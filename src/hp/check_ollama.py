"""Szybka diagnostyka Ollamy: python -m hp.check_ollama [model]
Sprawdza (1) czy serwer działa i model jest pobrany, (2) czy okno kontekstu naprawdę jest używane (test ucinania promptu),
(3) jak model koduje jeden fragment Gdyni (problemy i działania) — zanim ruszysz cały korpus."""
from __future__ import annotations

import sys
import time

import yaml

from . import ollama_client as OC, prompts as P, schema as S
from .extract_llm import chunk_text
from .ingest import load_pages


def main(model: str | None = None):
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    L = cfg["llm"]
    model = model or L["model_extract"]
    host = OC.host_url()
    print(f"Serwer: {host}\nModel:  {model}")
    try:
        import rapidfuzz  # noqa: F401
    except ImportError:
        print("UWAGA: brak pakietu rapidfuzz (pip install rapidfuzz) — dopasowanie rozmyte cytatów jest wyłączone, więcej pozycji zostanie odrzuconych.")
    try:
        tags = OC._request(f"{host}/api/tags", None, 15)
    except OC.OllamaError as e:
        print("BŁĄD:", e); return 1
    names = [m["name"] for m in tags.get("models", [])]
    print("Zainstalowane modele:", ", ".join(names) or "(brak)")
    if model not in names:
        print(f"BŁĄD: model {model} nie jest pobrany. Uruchom:  ollama pull {model}"); return 1
    print("Digest modelu:", OC.model_digest(model, host))

    # 2) test ucinania: długi prompt (~9 tys. tokenów) musi być w całości widziany przy num_ctx z configu
    filler = "Mieszkaniowy zasób gminy tworzą lokale komunalne. " * 360
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    msgs = [{"role": "system", "content": "Odpowiedz JSON {\"ok\": true}."}, {"role": "user", "content": filler}]
    t = time.time()
    try:
        _, meta = OC.chat_json(model, msgs, schema, num_ctx=L["num_ctx"], num_predict=50, temperature=0, host=host)
        n = meta["prompt_eval_count"]
        print(f"Test okna: prompt_eval_count={n} przy num_ctx={L['num_ctx']} ({time.time() - t:.0f} s)  ->",
              "OK, model widzi cały prompt" if n and n > 4200 else "UWAGA: policzono ≤4096 tokenów — okno nadal jest ucinane (sprawdź num_ctx / wersję Ollamy)")
    except OC.OllamaError as e:
        print("Test okna nie powiódł się:", e)

    # 3) jeden prawdziwy fragment
    try:
        pages = load_pages("WPGMZ_Gdynia_2022-2026", cfg["paths"]["interim"])
    except FileNotFoundError:
        print("Brak data/interim dla Gdyni — pomijam test kodowania (uruchom: python -m hp.cli ingest)."); return 0
    # strona 4 PDF-a Gdyni: obowiązek gminy wobec eksmitowanych (problem); strona 9: wstrzymanie sprzedaży lokali (działanie)
    def chunk_of(page):
        text = "\n".join(f"[[strona {p.page}]]\n{p.text}" for p in pages if p.page == page)
        return chunk_text(text, L.get("chunk_chars", 4500))[0]
    for kind, cls, page in (("problems", S.LlmProblems, 4), ("actions", S.LlmActions, 9)):
        chunk = chunk_of(page)
        t = time.time()
        try:
            data, meta = OC.chat_json(model, P.items_messages(kind, chunk), S.inline_schema(cls), num_ctx=L["num_ctx"],
                                      num_predict=L.get("num_predict", 3000), temperature=0, seed=L.get("seed", 7), host=host)
        except OC.OllamaError as e:
            print(f"[{kind}] BŁĄD: {e}"); continue
        data = S.decode_labels(data)
        rate = (meta["eval_count"] or 0) / max(meta["seconds"], 0.1)
        print(f"\n[{kind}] {len(data[kind])} pozycji, {time.time() - t:.0f} s, tokeny: prompt={meta['prompt_eval_count']} odp.={meta['eval_count']} (≈ {rate:.1f} tok/s łącznie z przetwarzaniem promptu)")
        if rate < 5:
            print("  UWAGA: poniżej ~5 tok/s — prawdopodobnie CPU. Pełny korpus potrwa bardzo długo; rozważ GPU, mniejszy num_ctx/chunk_chars albo wyłączenie facts.")
        for x in data[kind][:6]:
            print("  -", x.get("category") or x.get("instrument"), "|", x["quote"][:110])
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
