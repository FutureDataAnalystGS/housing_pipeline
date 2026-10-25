"""Etap 4. Ekstrakcja strukturalna LLM (Anthropic API, wymuszone wywołanie narzędzia = JSON zgodny ze schematem).

Zasady metodologiczne wbudowane w kod:
  * temperatura 0, wersjonowany prompt, pełne cache'owanie odpowiedzi (replikowalność i niski koszt iteracji);
  * każdy blok = osobne wywołanie na właściwych sekcjach dokumentu (mniejszy kontekst -> mniej błędów);
  * każdy kodowany fakt ma cytat + stronę; cytaty są weryfikowane programowo (verify_evidence);
  * w razie błędu walidacji Pydantic — jedna automatyczna poprawka z komunikatem błędu.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from . import schema as S
from .ingest import Page
from .segment import Section, element_texts

SYSTEM = """Jesteś asystentem badawczym kodującym polskie dokumenty samorządowe (strategie rozwoju miast oraz wieloletnie programy gospodarowania mieszkaniowym zasobem gminy) według księgi kodowej v0.1.

Zasady bezwzględne:
1. Koduj WYŁĄCZNIE to, co wprost wynika z podanego tekstu. Nie uzupełniaj wiedzą zewnętrzną i nie zgaduj.
2. Liczby przepisuj dokładnie, wraz z jednostką i datą odniesienia. Nie przeliczaj i nie sumuj sam — jeśli dokument nie podaje sumy, a pole jej wymaga, ustaw status 'not_present'. Wyjątek: pola 'Suma … w okresie programu' wolno obliczyć z tabeli rocznej, jeśli wszystkie lata są podane; zaznacz to w cytacie.
3. Status: 'found' = wartość wprost w tekście; 'not_present' = tekst nie zawiera tej informacji; 'unclear' = informacja jest niejednoznaczna lub sprzeczna (opisz w cytacie).
4. Każda wartość ze statusem 'found' MUSI mieć co najmniej jeden dowód: numer strony z markera [[strona N]] i DOSŁOWNY cytat (do 35 słów) skopiowany z tekstu bez zmian.
5. Rozróżniaj POLITYKĘ mieszkaniową (zasób gminy, dostępność, wykluczenie, wsparcie) od ZABUDOWY MIESZKANIOWEJ jako funkcji przestrzennej. Samo „tereny zabudowy mieszkaniowej” nie jest problemem ani działaniem polityki mieszkaniowej; koduj je tylko, gdy dokument formułuje problem/cel dotyczący mieszkalnictwa (wtedy wymiar = spatial).
6. Problemy (P-kody) = elementy DIAGNOZY (stan rzeczy). Cele i działania (I-kody) = to, co gmina deklaruje zrobić. Nie mieszaj tych kategorii.
7. Jeśli w tekście brak treści do zakodowania, zwróć puste listy i relevant=false. Lepiej pominąć niż zmyślić."""


def _stable(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def cache_key(*parts) -> str:
    return hashlib.sha256("||".join(_stable(p) if not isinstance(p, str) else p for p in parts).encode()).hexdigest()[:32]



def make_client():
    """Adres lokalnego serwera Ollama."""
    import os
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")




def call_model(client, model: str, user: str, json_schema: dict, *,
               max_tokens: int, temperature: float | None,
               system: str = SYSTEM, retries: int = 3) -> dict:
    """Wywołuje lokalny model Ollama i odczytuje wynik JSON."""
    import urllib.request
    import urllib.error

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": json_schema,
        "options": {"num_predict": min(max_tokens, 2048)},
    }

    if temperature is not None:
        payload["options"]["temperature"] = temperature

    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                f"{client}/api/chat",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(request, timeout=600) as response:
                    result = json.loads(
                        response.read().decode("utf-8")
                    )
            except urllib.error.HTTPError as e:
                details = e.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Ollama HTTP {e.code}: {details}"
                ) from e

            print(
                f"[OLLAMA] done_reason={result.get('done_reason')}, "
                f"eval_count={result.get('eval_count')}, "
                f"prompt_eval_count={result.get('prompt_eval_count')}"
            )

            content = result.get("message", {}).get("content", "")
            data = json.loads(content)

            if not isinstance(data, dict):
                raise ValueError("Ollama nie zwróciła obiektu JSON.")

            return data

        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)

    raise RuntimeError("Nie udało się uzyskać odpowiedzi z Ollama.")





def run_block(client, cfg: dict, name: str, model_cls: type[BaseModel], user_text: str, header: str,
              cache_dir: Path, force: bool = False) -> dict:
    schema = S.inline_schema(model_cls)
    if name.startswith("items_part_"):
        instruction = (
            "Przeanalizuj dokładnie cały fragment dokumentu i wyodrębnij "
            "wszystkie występujące w nim problemy mieszkaniowe, cele oraz działania. "
            "Nie pomijaj list, punktów numerowanych, diagnoz, opisów stanu istniejącego "
            "ani problemów opisanych pośrednio. "
            "W polu problems umieść zidentyfikowane problemy dotyczące mieszkalnictwa, "
            "zasobu komunalnego, dostępności mieszkań, najmu, pustostanów, stanu "
            "technicznego budynków i potrzeb mieszkańców. Przypisz każdemu problemowi "
            "odpowiednią kategorię ze schematu. "
            "W polu goals umieść cele programu, a w polu actions konkretne działania. "
            "Nie traktuj braku nagłówka 'Problemy' jako dowodu, że problemy nie występują. "
            "Każda pozycja musi mieć poparcie w tekście źródłowym: zachowaj dosłowny "
            "cytat i numer strony z oznaczenia [[strona N]]. Nie wymyślaj treści. "
            "Jeżeli fragment nie zawiera żadnych problemów, zwróć pustą listę problems."
        )
    else:
        instruction = f"Wypełnij schemat dla bloku „{name}”."

    user = f"{header}\n\n<dokument>\n{user_text}\n</dokument>\n\n{instruction}"
    key = cache_key(cfg["prompt_version"], cfg["model_extract"], SYSTEM, user, schema)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"{name}.{key}.json"

    if f.exists() and not force:
        return json.loads(f.read_text(encoding="utf-8"))

    print(f"[LLM] start: {name}, chars={len(user)}", flush=True)

    data = call_model(
        client, cfg["model_extract"], user, schema,
        max_tokens=cfg["max_tokens"],
        temperature=cfg.get("temperature")
    )

    print(f"[LLM] koniec: {name}", flush=True)

    try:
        data = model_cls.model_validate(data).model_dump(mode="json")
    except ValidationError as e:
        fix = (
            user
            + f"\n\nTwoja poprzednia odpowiedź nie przeszła walidacji schematu:\n"
            + f"{str(e)[:1500]}\nPopraw i zwróć kompletny wynik."
        )
        data = call_model(
            client, cfg["model_extract"], fix, schema,
            max_tokens=cfg["max_tokens"],
            temperature=cfg.get("temperature")
        )
        data = model_cls.model_validate(data).model_dump(mode="json")

    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data



def _pages_text(pages: list[Page]) -> str:
    return "\n".join(f"[[strona {p.page}]]\n{p.text}" for p in pages)


def merge_housing_items(parts: list[dict]) -> dict:
    """Łączy wyniki ekstrakcji z kilku fragmentów dokumentu."""
    merged = {
        "relevant": any(p.get("relevant", False) for p in parts),
        "problems": [],
        "goals": [],
        "actions": [],
    }

    for key in ("problems", "goals", "actions"):
        seen = set()

        for part in parts:
            for item in part.get(key, []):
                evidence = item.get("evidence") or {}
                identity = (
                    str(item.get("statement", "")).strip().casefold(),
                    str(evidence.get("quote", "")).strip().casefold(),
                    evidence.get("page"),
                )

                if identity not in seen:
                    seen.add(identity)
                    merged[key].append(item)

    return merged

def run_document(client, cfg: dict, doc_id: str, doc_type: str, pages: list[Page], sections: list[Section] | None,
                 passages: list | None, md: dict, extracted_dir: str | Path, force: bool = False) -> dict:
    """Zwraca i zapisuje rekord dokumentu: metadane + bloki faktów + pozycje + audyt cytatów."""
    extracted_dir = Path(extracted_dir)
    cache_dir = extracted_dir / "_cache" / doc_id
    header = f"<meta doc_id=\"{doc_id}\" typ=\"{doc_type}\" okres=\"{md.get('period_start')}–{md.get('period_end')}\"/>"
    out: dict[str, Any] = {"doc_id": doc_id, "doc_type": doc_type, "metadata": md, "blocks": {}, "items": None}

    if doc_type == "WPGMZ":
        el = element_texts(sections or [])
        fallback = len(el) < 5
        for name, cls, elements in S.WPGMZ_BLOCKS:
            txt = _pages_text(pages) if fallback else "\n\n".join(el[e] for e in elements if e in el)
            if not txt.strip():
                txt = _pages_text(pages)
            out["blocks"][name] = run_block(client, cfg, name, cls, txt, header, cache_dir, force)
        items_text = _pages_text(pages)
    else:
        txt = "\n\n".join(p.text for p in (passages or []))
        name, cls, _ = S.STRATEGY_FRAME_BLOCK
        out["blocks"][name] = run_block(client, cfg, name, cls, txt, header, cache_dir, force) if txt.strip() else None
        items_text = txt

    if not items_text.strip():
        out["items"] = {
            "relevant": False,
            "problems": [],
            "goals": [],
            "actions": [],
        }
    elif doc_type == "WPGMZ":
        item_parts = []

        # Analizujemy po 4 strony w jednym wywołaniu modelu.
        chunk_size = 4

        for start in range(0, len(pages), chunk_size):
            chunk_pages = pages[start:start + chunk_size]
            chunk_text = _pages_text(chunk_pages)

            if not chunk_text.strip():
                continue

            part = run_block(
                client,
                cfg,
                f"items_part_{start + 1}",
                S.HousingItems,
                chunk_text,
                header,
                cache_dir,
                force,
            )
            item_parts.append(part)

        out["items"] = merge_housing_items(item_parts)
    else:
        out["items"] = run_block(
            client,
            cfg,
            "items",
            S.HousingItems,
            items_text,
            header,
            cache_dir,
            force,
        )
    out["audit"] = verify_evidence(out, pages)
    out["versions"] = dict(prompt_version=cfg["prompt_version"], model=cfg["model_extract"], run_date=date.today().isoformat(),
                           segmentation_fallback=(doc_type == "WPGMZ" and len(element_texts(sections or [])) < 5))
    (extracted_dir / f"{doc_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ------------------------------------------------------------------ weryfikacja cytatów
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
    except ImportError:                      # awaryjnie: tylko dopasowanie dokładne
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
