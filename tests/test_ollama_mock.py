"""Testy warstwy Ollama na ATRAPIE serwera (bez modelu i bez sieci).
Sprawdzają mechanikę: czy okno kontekstu jest ustawiane, czy definicje kodów trafiają do promptu, czy schemat wymaga wszystkich pól,
czy ucięta odpowiedź skutkuje podziałem fragmentu, a zmyślony cytat jest odrzucany. NIE oceniają jakości prawdziwego modelu — do tego służy hp.evaluate."""
import json, os, re, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src")); sys.path.insert(0, os.path.dirname(__file__))
import pytest

from hp import aggregate as A, extract_llm as E, schema as S
from hp.ingest import load_pages
from hp.segment import segment_wpgmz

HAVE = os.path.exists("data/interim/WPGMZ_Gdynia_2022-2026.pages.jsonl")
need_pages = pytest.mark.skipif(not HAVE, reason="uruchom najpierw etap ingest")
CALLS: list[dict] = []
BEHAVIOUR = {"truncate_over": None, "fake_quote": False}


def skeleton(s):
    if "enum" in s:
        return "not_present" if "not_present" in s["enum"] else s["enum"][0]
    t = s.get("type")
    if t == "object":
        return {k: skeleton(v) for k, v in s["properties"].items()}
    if t == "array":
        return []
    if "anyOf" in s:
        return None
    return {"string": "", "boolean": False, "integer": 0, "number": 0}.get(t)


def sentence(text, needle):
    text = re.sub(r"\s+", " ", text)                      # zdania w PDF-ach są łamane na wiersze
    m = re.search(rf"[^.]*{needle}[^.]*", text)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:7b", "digest": "abc123"}]})

    def do_POST(self):
        p = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CALLS.append(p)
        user = p["messages"][-1]["content"]
        props = p["format"]["properties"]
        page = (re.findall(r"\[\[strona (\d+)\]\]", user) or ["1"])[0]
        if BEHAVIOUR["truncate_over"] and len(user) > BEHAVIOUR["truncate_over"] and "actions" in props:
            return self._chat(p, "{", "length", 500, 3000)
        if "results" in props:                                  # tryb „kandydaci”: lista „[n] zdanie”
            is_actions = "DZIAŁANIE" in p["messages"][0]["content"]
            res = []
            for n, txt in re.findall(r"^\[(\d+)\] (.*)$", user, re.M):
                lab = "NONE"
                if is_actions and ("nie będzie prowadzon" in txt or "wstrzym" in txt):
                    lab = "I21"
                elif is_actions and "termomodernizac" in txt.lower():
                    lab = "I07"
                elif not is_actions and ("eksmisj" in txt or "niepodłączonych" in txt):
                    lab = "P05" if "eksmisj" in txt else "P02"
                res.append(dict(id=int(n), label=lab))
            return self._chat(p, json.dumps({"results": res}), "stop", 1200, 60)
        if "problems" in props:
            q = "To zdanie nie istnieje w dokumencie" if BEHAVIOUR["fake_quote"] else sentence(user, "każda wykonywana w mieście eksmisja")
            out = {"problems": [dict(quote=q, page=int(page), category="P05 Niedobór zasobu komunalnego i socjalnego", severity="key", statement="Eksmisje obciążają gminę.")] if q else []}
        elif "actions" in props:
            q = sentence(user, "nie będzie prowadzona")
            out = {"actions": [dict(quote=q, page=int(page), instrument="I21 Sprzedaż lokali", status="existing", stance="restrict", description="Wstrzymanie sprzedaży.",
                                    target_text=None, budget_pln=None, period=None, responsible=None)] if q else []}
        elif "goals" in props:
            q = sentence(user, "zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących")
            out = {"goals": [dict(quote=q, page=int(page), level="strategic_goal", dimension="social", statement="Potrzeby najbardziej potrzebujących.")] if q else []}
        else:
            out = skeleton(p["format"])
        self._chat(p, json.dumps(out, ensure_ascii=False), "stop", 1500, 200)

    def _chat(self, p, content, reason, pec, ec):
        """Odpowiedź w formacie NDJSON (stream=True), tak jak robi to Ollama."""
        half = len(content) // 2
        lines = [{"message": {"content": content[:half]}, "done": False},
                 {"message": {"content": content[half:]}, "done": True, "done_reason": reason, "prompt_eval_count": pec, "eval_count": ec}]
        b = ("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n").encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _send(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


@pytest.fixture(scope="module")
def host():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


CFG = dict(prompt_version="test", model_extract="qwen2.5:7b", num_ctx=12288, num_predict=3000, chunk_chars=4500, facts_chunk_chars=9000, seed=7, temperature=0)


def _run(host, tmp_path, **over):
    CALLS.clear()
    pages = load_pages("WPGMZ_Gdynia_2022-2026", "data/interim")
    return E.run_document(host, {**CFG, **over}, "WPGMZ_Gdynia_2022-2026", "WPGMZ", pages, segment_wpgmz(pages), None,
                          dict(period_start=2022, period_end=2026), tmp_path, force=True)


@need_pages
def test_prompt_carries_codebook_and_context_window_is_set(host, tmp_path):
    rec = _run(host, tmp_path, mode="chunks")
    assert all(c["options"]["num_ctx"] == 12288 and c["options"]["seed"] == 7 for c in CALLS)       # okno kontekstu zawsze jawne
    sys_prompts = [c["messages"][0]["content"] for c in CALLS if "problems" in c["format"]["properties"]]
    assert sys_prompts and "P05 Niedobór zasobu komunalnego i socjalnego —" in sys_prompts[0]      # definicje kodów są w prompcie
    facts = [c for c in CALLS if "stock" in c["format"]["properties"]][0]
    assert "stock.units_total [liczba]" in facts["messages"][0]["content"]                           # opisy pól są w prompcie
    assert facts["format"]["properties"]["stock"]["required"]                                      # wszystkie pola wymagane
    assert rec["versions"]["model_digest"] == "abc123"


@need_pages
def test_items_are_found_verified_and_page_resolved(host, tmp_path):
    rec = _run(host, tmp_path, mode="chunks")
    it = rec["items"]
    assert it["problems"] and it["problems"][0]["category"] == "P05" and it["problems"][0]["evidence"]["page"] == 4
    assert it["actions"] and it["actions"][0]["instrument"] == "I21" and it["goals"]
    assert rec["audit"]["share_verified"] == 1.0 and not rec["audit"]["llm_errors"]


@need_pages
def test_truncated_answer_triggers_split_not_loss(host, tmp_path):
    BEHAVIOUR["truncate_over"] = 2200
    try:
        rec = _run(host, tmp_path, tasks=["actions"], mode="chunks")
    finally:
        BEHAVIOUR["truncate_over"] = None
    assert rec["items"]["actions"], "po podziale fragmentu akcja powinna zostać znaleziona"


@need_pages
def test_invented_quote_is_rejected(host, tmp_path):
    BEHAVIOUR["fake_quote"] = True
    try:
        rec = _run(host, tmp_path, tasks=["problems"], mode="chunks")
    finally:
        BEHAVIOUR["fake_quote"] = False
    assert not rec["items"]["problems"] and rec["audit"]["items_rejected"]


def test_number_without_support_in_quote_becomes_unclear():
    blocks = {"s": {"units_total": dict(value=9999, unit="lokale", ref_date=None, status="found", evidence=[dict(page=1, quote="tworzy 5 254 lokali gminnych")])},
              "t": {"area": dict(value=218584.97, unit="m2", ref_date=None, status="found", evidence=[dict(page=1, quote="218 584,97 m2")])},
              "u": {"costs": dict(value=4721000, unit="zł", ref_date=None, status="found", evidence=[dict(page=1, quote="Remonty ogółem brutto 4 721")])}}
    bad = E.check_numbers(blocks)
    assert [b["path"] for b in bad] == ["s.units_total"] and blocks["s"]["units_total"]["status"] == "unclear"
    assert blocks["t"]["area"]["status"] == "found" and blocks["u"]["costs"]["status"] == "found"


def test_schema_has_valid_types_and_all_required():
    s = S.inline_schema(S.WPGMZ_BLOCKS[0][1])
    f = s["properties"]["stock"]["properties"]["units_total"]
    assert f["type"] == "object" and set(f["required"]) == {"value", "unit", "ref_date", "status", "evidence"}
    assert "type" in S.inline_schema(S.Project)["properties"]                                         # pole o nazwie „type” nie ginie


def test_aggregate_city_fallback_and_thousand_pln():
    assert A.city_key_from_doc_id("WPGMZ_Biala_Podlaska_2021-2025") == A.city_key_from_doc_id("SR_Biała_Podlaska_2030") == "biala_podlaska"
    row = {}
    A._flat_block("repairs", {"outlays_repairs_total_pln": dict(value=4721, unit="tys. zł", status="found", evidence=[])}, row)
    assert row["repairs__outlays_repairs_total_pln"] == 4721000


def test_silent_server_gives_readable_timeout_not_traceback():
    """Serwer przyjmuje połączenie i milczy (jak przeciążona Ollama) -> OllamaTimeout z wskazówkami, szybko."""
    import socket, time
    from hp import ollama_client as OC
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    port = srv.getsockname()[1]
    t0 = time.time()
    with pytest.raises(OC.OllamaTimeout) as ei:
        OC.chat_json("m", [{"role": "user", "content": "x"}], {"type": "object"}, host=f"http://127.0.0.1:{port}", timeout=1, retries=0)
    srv.close()
    assert time.time() - t0 < 10 and "ollama ps" in str(ei.value)


def test_quality_flags_on_real_false_positives_from_gdynia_run():
    """Przykłady z prawdziwego przebiegu qwen2.5:7b na Gdyni (wiersze tabel, kwoty, definicja, podstawa prawna) vs prawdziwe problemy."""
    rows = ["Zgony i inne przyczyny 35 26 36 37 40", "liczba lokali planowanych do wybudowania 0 21 0 30 0",
            "remonty dachów wraz z obróbkami blacharskimi i remontem kominów 2 500 000", "6 000 000 5 000 000 3 000 000 2 800 000 2 800 000"]
    assert all("table_row" in E.quality_flags("problems", q) for q in rows)
    assert "definition_like" in E.quality_flags("problems", "budynek wymagający remontu bieżącego — budynek wymagający wykonania robót polegających na stałej")
    assert "legal_basis" in E.quality_flags("problems", "Stosownie do art. 21 ust. 1 ustawy z dnia 21 czerwca 2001 r. o ochronie praw lokatorów")
    good = ["każda wykonywana w mieście eksmisja wiąże się z obowiązkiem zapewnienia lokalu przez gminę",
            "Gmina Miasta Gdyni posiada 5 budynków niepodłączonych do kanalizacji sanitarnej"]
    assert all(not E.quality_flags("problems", q) for q in good)
    assert "table_row" not in E.quality_flags("actions", "termomodernizacja budynków objętych programem")


@need_pages
def test_fuzzy_quote_tolerates_list_numbering_but_rejects_invented_numbers():
    pytest.importorskip("rapidfuzz")
    pages = load_pages("WPGMZ_Gdynia_2022-2026", "data/interim")
    by_page = {p.page: E.fold_alnum(p.text) for p in pages}
    # model pominął numerację listy „1)” — dokładne dopasowanie zawodzi, rozmyte ma przejść
    q = "Gmina Miasta Gdyni jest właścicielem 150 budynków mieszkalnych, w tym: 103 budynki wybudowane przed 1945 rokiem"
    page, fuzzy = E.resolve_page(q, 3, by_page)
    assert page == 3
    # zmyślone liczby w wierszu tabeli nie mogą przejść
    page, _ = E.resolve_page("liczba wyroków do realizacji narastająco 630 750 770 790 910", 5, by_page)
    assert page is None


@need_pages
def test_candidate_mode_classifies_only_prose_sentences_and_keeps_exact_quotes(host, tmp_path):
    from hp import candidates as CAND
    rec = _run(host, tmp_path, tasks=["problems", "actions"])           # domyślny tryb: kandydaci
    cls_calls = [c for c in CALLS if "results" in c["format"]["properties"]]
    assert cls_calls and all(c["options"]["num_ctx"] == 12288 for c in cls_calls)
    prob_sent = [m for c in cls_calls if "PROBLEM" in c["messages"][0]["content"] for m in re.findall(r"^\[\d+\] (.*)$", c["messages"][-1]["content"], re.M)]
    assert prob_sent and not any(CAND.is_table_like(s) for s in prob_sent)     # wiersze tabel nie trafiają do klasyfikacji problemów
    it = rec["items"]
    assert any(p["category"] == "P05" and p["evidence"]["page"] == 4 for p in it["problems"])
    a21 = [a for a in it["actions"] if a["instrument"] == "I21"]
    assert a21 and a21[0]["stance"] == "restrict"                                # stance z heurystyki, nie z modelu
    assert rec["audit"]["share_verified"] == 1.0                                  # cytat = zdanie z dokumentu, więc zawsze dokładny
    st = rec["audit"]["candidate_stats"]
    assert st["problems"]["candidates"] > 10 and st["actions"]["batches"] >= 5


def test_candidate_units_keep_list_context_and_table_rule_is_not_too_broad():
    from hp import candidates as CAND
    assert not CAND.is_table_like("Gmina jest właścicielem 150 budynków mieszkalnych, w tym: 1) 103 budynki wybudowane przed 1945 rokiem 2) 39 budynków wybudowanych w latach 1945 -1980,")
    assert CAND.is_table_like("remonty dachów wraz z obróbkami blacharskimi i remontem kominów 2 500 000")
    assert CAND.is_table_like("Zgony i inne przyczyny 35 26 36 37 40")
    assert not CAND.is_table_like("Program obowiązuje do 2026")
