"""Etap 4. Ekstrakcja strukturalna LLM — wersja dla lokalnego modelu (Ollama), bez płatnego API.

Co jest inaczej niż w wersji „jedno wielkie wywołanie”:
  * definicje kodów P/I i opisy pól są w PROMPCIE (Ollama używa schematu tylko jako gramatyki wyjścia);
  * każde wywołanie = jeden mały fragment (domyślnie ~4,5 tys. znaków) i JEDNO zadanie (problemy / działania / cele);
  * wszystkie pola schematu są wymagane, a okno kontekstu (num_ctx) jest ustawiane jawnie;
  * pozycje bez cytatu odnajdywalnego w dokumencie są odrzucane (ochrona przed zmyślaniem małego modelu);
  * liczby bez pokrycia w cytacie dostają status „unclear”; słownik problemów działa jako siatka bezpieczeństwa (possible_misses);
  * pełne cache'owanie: przerwany przebieg można wznowić, a powtórka daje te same wyniki (seed, temperatura 0).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from . import ollama_client as OC
from . import prompts as P
from . import schema as S
from .ingest import Page
from . import candidates as CAND
from .lexicon import baseline_problems
from .segment import Section, element_texts

SYSTEM = P.BASE                       # zgodność wsteczna (summarize.py, test_items.py)


def make_client() -> str:
    """Adres lokalnego serwera Ollama (OLLAMA_HOST albo http://localhost:11434)."""
    return OC.host_url()


def _stable(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def cache_key(*parts) -> str:
    return hashlib.sha256("||".join(_stable(p) if not isinstance(p, str) else p for p in parts).encode()).hexdigest()[:32]


def call_model(client, model: str, user: str, json_schema: dict, *, max_tokens: int, temperature: float | None,
               system: str = SYSTEM, retries: int = 2) -> dict:
    """Prosta powłoka zgodna ze starym API (używana przez summarize.llm_summary)."""
    data, _ = OC.chat_json(model, [{"role": "system", "content": system}, {"role": "user", "content": user}], json_schema,
                           num_ctx=16384, num_predict=min(max_tokens, 3000), temperature=temperature, host=client, retries=retries)
    return data


# ------------------------------------------------------------------ tekst i fragmenty
def _pages_text(pages: list[Page]) -> str:
    return "\n".join(f"[[strona {p.page}]]\n{p.text}" for p in pages)


_MARK = re.compile(r"\[\[strona (\d+)\]\]")


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Dzieli tekst na fragmenty ≤ max_chars na granicach wierszy; każdy fragment zaczyna się od aktualnego znacznika strony."""
    chunks, cur, size, marker = [], [], 0, None
    for ln in text.split("\n"):
        m = _MARK.match(ln)
        if m:
            marker = ln
        if cur and size + len(ln) + 1 > max_chars:
            chunks.append("\n".join(cur))
            cur = [marker] if (marker and not m) else []
            size = sum(len(x) + 1 for x in cur)
        cur.append(ln)
        size += len(ln) + 1
    if cur:
        chunks.append("\n".join(cur))
    return [c for c in chunks if len(re.sub(r"\[\[strona \d+\]\]|\s", "", c)) > 60]


def split_half(chunk: str) -> list[str]:
    lines = chunk.split("\n")
    if len(lines) > 3:
        mid = len(lines) // 2
        marker = next((l for l in reversed(lines[:mid]) if _MARK.match(l)), None)
        second = lines[mid:] if (marker is None or _MARK.match(lines[mid])) else [marker] + lines[mid:]
        return ["\n".join(lines[:mid]), "\n".join(second)]
    mid = len(chunk) // 2
    cut = chunk.rfind(". ", 0, mid)
    cut = cut + 1 if cut > 0 else mid
    return [chunk[:cut], chunk[cut:]]


# ------------------------------------------------------------------ wywołanie z cache i jedną poprawką
def _call(host: str, cfg: dict, messages: list[dict], model_cls: type[BaseModel], cache_dir: Path, name: str, force: bool) -> dict:
    schema = S.inline_schema(model_cls)
    key = cache_key(cfg["prompt_version"], cfg["model_extract"], cfg.get("num_ctx", 12288), cfg.get("seed", 7), messages, schema)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"{name}.{key}.json"
    if f.exists() and not force:
        return json.loads(f.read_text(encoding="utf-8"))
    kw = dict(num_ctx=cfg.get("num_ctx", 12288), num_predict=cfg.get("num_predict", 3000), temperature=cfg.get("temperature", 0.0),
              seed=cfg.get("seed", 7), host=host, timeout=cfg.get("timeout", 600))
    data, _ = OC.chat_json(cfg["model_extract"], messages, schema, **kw)
    data = S.decode_labels(data)
    try:
        model_cls.model_validate(data)
    except ValidationError as e:                     # jedna automatyczna poprawka z komunikatem błędu
        fix = messages + [{"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                          {"role": "user", "content": f"Odpowiedź nie przeszła walidacji schematu:\n{str(e)[:1200]}\nPopraw i zwróć kompletny JSON."}]
        data, _ = OC.chat_json(cfg["model_extract"], fix, schema, **kw)
        data = S.decode_labels(data)
        model_cls.model_validate(data)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


ITEM_SPEC = {"problems": (S.LlmProblems, "problems", S.to_problem_item),
             "goals": (S.LlmGoals, "goals", S.to_goal_item),
             "actions": (S.LlmActions, "actions", S.to_action_item)}


def run_items_chunk(host, cfg, kind, chunk, header, cache_dir, force, errors, depth=0) -> list[dict]:
    cls, key, conv = ITEM_SPEC[kind]
    try:
        data = _call(host, cfg, P.items_messages(kind, chunk, header, cfg.get("prompt_profile", "v1")), cls, cache_dir, f"items_{kind}", force)
    except (OC.TruncatedOutput, OC.PromptTooLong) as e:       # dzielimy fragment na pół i próbujemy ponownie
        if depth >= 2:
            errors.append(dict(kind=kind, error=str(e), chars=len(chunk)))
            return []
        return [x for part in split_half(chunk) for x in run_items_chunk(host, cfg, kind, part, header, cache_dir, force, errors, depth + 1)]
    return [conv(x) for x in data.get(key, [])]


# ------------------------------------------------------------------ tryb „kandydaci”
def _batches(units: list, max_chars: int, max_n: int) -> list[list]:
    out, cur, size = [], [], 0
    for u in units:
        if cur and (size + len(u.text) > max_chars or len(cur) >= max_n):
            out.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += len(u.text)
    if cur:
        out.append(cur)
    return out


def _item_from_unit(kind: str, label: str, u) -> dict:
    t = u.text
    ev = dict(page=u.page, quote=t)
    if kind == "problems":
        return dict(category=label, statement=t[:200], severity=CAND.severity(t), quantified=bool(re.search(r"\d", t)), quant_text=None,
                    affected_groups=[], section=None, evidence=ev)
    b = CAND.budget_pln(t)
    return dict(instrument=label, description=t[:200], stance=CAND.act_stance(t), status=CAND.act_status(t), named_instrument=True,
                has_target_value=bool(re.search(r"\d", t)), target_text=None, has_budget_or_source=b is not None, budget_pln=b,
                has_deadline_or_owner=bool(re.search(r"20[2-3]\d|Prezydent|ZLiBK|ZBM|zarząd", t)), responsible=None, period=None,
                addresses_problems=[], link_explicit=False, evidence=ev)


def run_candidates(host, cfg, kind, units, cache_dir, force, errors, depth=0) -> tuple[list[dict], dict]:
    """Klasyfikuje zdania-kandydatów partiami (kilka zdań na wywołanie, krótka odpowiedź)."""
    cls = S.ClassifyProblems if kind == "problems" else S.ClassifyActions
    items: list[dict] = []
    stats = dict(candidates=len(units), accepted=0, batches=0)
    lcfg = {**cfg, "num_predict": cfg.get("cand_num_predict", 700)}

    def run(batch, depth=0):
        stats["batches"] += 1
        try:
            data = _call(host, lcfg, P.classify_messages(kind, batch), cls, cache_dir, f"cand_{kind}", False if not force else True)
        except (OC.TruncatedOutput, OC.PromptTooLong) as e:
            if len(batch) > 1 and depth < 3:
                mid = len(batch) // 2
                return run(batch[:mid], depth + 1) + run(batch[mid:], depth + 1)
            errors.append(dict(kind=f"cand_{kind}", error=str(e), chars=sum(len(u.text) for u in batch)))
            return []
        out = []
        for r in data.get("results", []):
            i, lab = r.get("id"), r.get("label")
            if isinstance(i, int) and 1 <= i <= len(batch) and lab and lab != "NONE":
                out.append(_item_from_unit(kind, lab, batch[i - 1]))
        return out

    for k, batch in enumerate(_batches(units, cfg.get("cand_batch_chars", 3200), cfg.get("cand_batch_max", 10)), 1):
        items += run(batch)
        print(f"[LLM] {kind}: partia {k} ({len(batch)} zdań) -> {len(items)} pozycji dotąd", flush=True)
    stats["accepted"] = len(items)
    return items, stats


# ------------------------------------------------------------------ bloki faktów (WPGMZ, ramka strategii)
_RANK = {"found": 2, "unclear": 1, "not_present": 0}


def merge_facts(a, b):
    """Scala wyniki z kolejnych fragmentów: dla pola wygrywa status found > unclear > not_present; listy się sumują."""
    if isinstance(a, dict) and isinstance(b, dict):
        if "status" in a and "status" in b:
            return a if _RANK.get(a["status"], 0) >= _RANK.get(b["status"], 0) else b
        return {k: merge_facts(a.get(k), b.get(k)) if k in a and k in b else a.get(k, b.get(k)) for k in {**a, **b}}
    if isinstance(a, list) and isinstance(b, list):
        seen, out = set(), []
        for x in a + b:
            k = json.dumps(x, sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out
    return a if a not in (None, [], "") else b


def run_facts_block(host, cfg, name, cls, text, header, cache_dir, force, errors) -> dict:
    parts = chunk_text(text, cfg.get("facts_chunk_chars", 9000)) or [text]
    result = None
    for part in parts:
        try:
            data = _call(host, cfg, P.facts_messages(cls, part, header), cls, cache_dir, f"facts_{name}", force)
        except (OC.TruncatedOutput, OC.PromptTooLong) as e:
            errors.append(dict(kind=f"facts_{name}", error=str(e), chars=len(part)))
            continue
        result = data if result is None else merge_facts(result, data)
    return result or {}


# ------------------------------------------------------------------ weryfikacja cytatów i liczb
_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold_alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.translate(_FOLD).lower())


def _walk(node, path=""):
    if isinstance(node, dict):
        if "quote" in node and "page" in node and isinstance(node.get("quote"), str):
            yield path, node
        else:
            for k, v in node.items():
                yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def verify_evidence(record: dict, pages: list[Page], fuzzy_threshold: int = 90) -> dict:
    """Sprawdza, czy cytat występuje na wskazanej stronie (±1) po normalizacji; w razie braku — dopasowanie rozmyte."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        fuzz = None
    by_page = {p.page: fold_alnum(p.text) for p in pages}
    whole = "".join(by_page[k] for k in sorted(by_page))
    rows = []
    for path, ev in _walk({"blocks": record.get("blocks"), "items": record.get("items")}):
        q = fold_alnum(ev["quote"])
        pg = ev.get("page")
        near = "".join(by_page.get(p, "") for p in ((pg - 1, pg, pg + 1) if isinstance(pg, int) else ()))
        exact_page = bool(q) and q in near
        exact_doc = bool(q) and q in whole
        score = 100 if exact_doc else (fuzz.partial_ratio(q, near or whole) if (fuzz and q) else 0)
        rows.append(dict(path=path, page=pg, exact_on_page=exact_page, exact_in_doc=exact_doc, fuzzy=round(score, 1),
                         verified=exact_page or exact_doc or score >= fuzzy_threshold))
    n = len(rows)
    return dict(n_evidence=n, share_verified=(sum(r["verified"] for r in rows) / n if n else None),
                share_exact_on_cited_page=(sum(r["exact_on_page"] for r in rows) / n if n else None),
                unverified=[r for r in rows if not r["verified"]])


def resolve_page(quote: str, claimed: int | None, by_page: dict[int, str]) -> tuple[int | None, bool]:
    """Zwraca (strona, czy_dopasowanie_rozmyte). Model często myli numer strony, pomija numerację list („1)”) albo skleja wiersze —
    dlatego po dopasowaniu dokładnym próbujemy dopasowania rozmytego (≥92%) w okolicy wskazanej strony."""
    q = fold_alnum(quote)
    if len(q) < 12:
        return None, False
    if isinstance(claimed, int):
        for p in (claimed, claimed - 1, claimed + 1):
            if q in by_page.get(p, ""):
                return p, False
    for p, t in by_page.items():
        if q in t:
            return p, False
    if len(q) >= 25:
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return None, False
        near = [p for p in range(claimed - 2, claimed + 3) if p in by_page] if isinstance(claimed, int) else []
        cands = near or (list(by_page) if len(by_page) <= 60 else [])
        best = max(((fuzz.partial_ratio(q, by_page[p]), p) for p in cands), default=(0, None))
        if best[0] >= 92:
            return best[1], True
    return None, False


_CUES = CAND._P_CUES


def quality_flags(kind: str, quote: str, check_cue: bool = True) -> list[str]:
    """Reguły jakości dla cytatu pozycji. `table_row` = wiersz tabeli/kwoty (to wskaźnik do bloków faktów, nie problem ani cel)."""
    q = " ".join(quote.split())
    flags = []
    if CAND.is_table_like(q):
        flags.append("table_row")
    if len(re.findall(r"[^\W\d_]{4,}", q)) < 4:
        flags.append("fragment")
    if re.match(r"^[^.]{3,80}\s[—–-]\s", q):
        flags.append("definition_like")
    if re.search(r"\bart\.\s*\d+|Stosownie do|Dz\.\s*U\.", q):
        flags.append("legal_basis")
    if kind == "problems" and check_cue and not _CUES.search(q):
        flags.append("no_problem_cue")
    return flags


def number_supported(value, evidence: list[dict]) -> bool:
    """Czy cyfry wartości występują w cytacie? (5254 ↔ „5 254”; 85,41 ↔ „85,41%”; tys. zł ↔ ucięte zera)."""
    if value is None or float(value) == 0:
        return True
    digits = re.sub(r"\D", "", " ".join(e.get("quote", "") for e in evidence))
    v = float(value)
    cand = re.sub(r"\D", "", str(int(v)) if v.is_integer() else repr(round(v, 2))).rstrip("0")
    return bool(cand) and cand in digits


def check_numbers(blocks: dict) -> list[dict]:
    bad = []

    def walk(node, path):
        if isinstance(node, dict):
            if "status" in node and "value" in node and isinstance(node.get("value"), (int, float)) and not isinstance(node.get("value"), bool):
                if node["status"] == "found" and not number_supported(node["value"], node.get("evidence") or []):
                    bad.append(dict(path=path, value=node["value"]))
                    node["status"] = "unclear"
            else:
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else k)
    walk(blocks, "")
    return bad


# ------------------------------------------------------------------ dokument
def _dedupe(items: list[dict], key_field: str) -> list[dict]:
    seen, out = set(), []
    for it in items:
        k = (it.get(key_field), fold_alnum(it["evidence"]["quote"])[:60])
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def run_document(client, cfg: dict, doc_id: str, doc_type: str, pages: list[Page], sections: list[Section] | None,
                 passages: list | None, md: dict, extracted_dir: str | Path, force: bool = False) -> dict:
    """Zwraca i zapisuje rekord dokumentu: metadane + bloki faktów + pozycje + audyt."""
    host = client
    extracted_dir = Path(extracted_dir)
    cache_dir = extracted_dir / "_cache" / doc_id
    header = f"<meta doc_id=\"{doc_id}\" typ=\"{doc_type}\" okres=\"{md.get('period_start')}–{md.get('period_end')}\"/>\n"
    errors: list[dict] = []
    out: dict[str, Any] = {"doc_id": doc_id, "doc_type": doc_type, "metadata": md, "blocks": {}, "items": None}

    use_facts = cfg.get("facts", True)             # facts: false = tylko problemy/cele/działania (szybki test)
    if doc_type == "WPGMZ":
        el = element_texts(sections or [])
        fallback = len(el) < 5
        for name, cls, elements in (S.WPGMZ_BLOCKS if use_facts else []):
            txt = _pages_text(pages) if fallback else "\n\n".join(el[e] for e in elements if e in el)
            if not txt.strip():
                txt = _pages_text(pages)
            out["blocks"][name] = run_facts_block(host, cfg, name, cls, txt, header, cache_dir, force, errors)
            print(f"[LLM] {doc_id}: blok {name} gotowy", flush=True)
        items_text = _pages_text(pages)
    else:
        top = sorted(passages or [], key=lambda p: -p.score)
        picked, total = [], 0
        for p in top:                                               # ramka strategii: najtrafniejsze pasaże w limicie
            if total + len(p.text) <= cfg.get("facts_chunk_chars", 9000):
                picked.append(p)
                total += len(p.text)
        frame_text = "\n\n".join(p.text for p in sorted(picked, key=lambda x: x.page_start))
        name, cls, _ = S.STRATEGY_FRAME_BLOCK
        out["blocks"][name] = run_facts_block(host, cfg, name, cls, frame_text, header, cache_dir, force, errors) if (frame_text.strip() and use_facts) else None
        items_text = "\n\n".join(p.text for p in (passages or []))

    tasks = cfg.get("tasks", ["problems", "actions", "goals"])
    mode = cfg.get("mode", "candidates")                  # candidates = klasyfikacja zdań wybranych słownikiem; chunks = otwarte wyszukiwanie we fragmentach
    cand_kinds = [k for k in tasks if mode == "candidates" and k in ("problems", "actions")]
    chunk_kinds = [k for k in tasks if k not in cand_kinds]
    by_kind: dict[str, list[dict]] = {k: [] for k in ("problems", "goals", "actions")}
    misses: list[dict] = []
    cand_stats: dict[str, dict] = {}
    if cand_kinds:
        units = CAND.build_units(pages)
        for kind in cand_kinds:
            cands = CAND.select(units, kind, require_housing=(doc_type == "SR"))
            by_kind[kind], cand_stats[kind] = run_candidates(host, cfg, kind, cands, cache_dir, force, errors)
    chunks = chunk_text(items_text, cfg.get("chunk_chars", 4500)) if (items_text.strip() and chunk_kinds) else []
    for i, ch in enumerate(chunks, 1):
        found_p: list[dict] = []
        for kind in chunk_kinds:
            items = run_items_chunk(host, cfg, kind, ch, header, cache_dir, force, errors)
            by_kind[kind] += items
            if kind == "problems":
                found_p = items
        if "problems" in chunk_kinds:
            gap = baseline_problems(ch) - {p["category"] for p in found_p}
            if gap:
                pg = _MARK.findall(ch)
                misses.append(dict(pages=f"{pg[0]}–{pg[-1]}" if pg else "?", categories=sorted(gap)))
        print(f"[LLM] {doc_id}: fragment {i}/{len(chunks)}", flush=True)

    by_page = {p.page: fold_alnum(p.text) for p in pages}
    rejected: list[dict] = []
    for kind, field in (("problems", "category"), ("goals", "level"), ("actions", "instrument")):
        ok = []
        for it in _dedupe(by_kind[kind], field):
            q = it["evidence"]["quote"]
            pg, fuzzy = resolve_page(q, it["evidence"].get("page"), by_page)
            flags = quality_flags(kind, q, check_cue=not (kind == "problems" and mode == "candidates"))
            if pg is None:
                rejected.append(dict(kind=kind, quote=q[:120], reason="cytat nie występuje w dokumencie"))
            elif "table_row" in flags and kind in ("problems", "goals"):
                rejected.append(dict(kind=kind, quote=q[:120], reason="wiersz tabeli/kwoty: to wskaźnik (blok faktów), nie problem ani cel"))
            else:
                it["evidence"]["page"] = pg
                if fuzzy:
                    flags.append("fuzzy_quote")
                if kind == "actions":
                    flags = [f for f in flags if f not in ("table_row", "no_problem_cue")]    # wiersz budżetu bywa poprawnym działaniem
                it["flags"] = flags
                it["low_confidence"] = any(f in flags for f in ("definition_like", "legal_basis", "fragment", "no_problem_cue"))
                ok.append(it)
        by_kind[kind] = ok
    out["items"] = dict(relevant=any(by_kind.values()), **by_kind)
    unsupported = check_numbers(out["blocks"])
    out["audit"] = verify_evidence(out, pages)
    out["audit"].update(candidate_stats=cand_stats, items_low_confidence=sum(1 for k in by_kind.values() for x in k if x.get("low_confidence")), items_rejected=rejected, possible_misses=misses, numbers_unsupported=unsupported, llm_errors=errors)
    out["versions"] = dict(prompt_version=cfg["prompt_version"], model=cfg["model_extract"], model_digest=OC.model_digest(cfg["model_extract"], host),
                           num_ctx=cfg.get("num_ctx", 12288), seed=cfg.get("seed", 7), chunk_chars=cfg.get("chunk_chars", 4500), mode=mode,
                           run_date=date.today().isoformat(),
                           segmentation_fallback=(doc_type == "WPGMZ" and len(element_texts(sections or [])) < 5))
    (extracted_dir / f"{doc_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
