
import yaml
import json

from hp import ingest as I
from hp import schema as S
from hp.extract_llm import make_client, call_model

with open("config.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

pages = I.load_pages(
    "WPGMZ_Gdynia_2022-2026",
    cfg["paths"]["interim"],
)

text = "\n".join(
    f"[[strona {p.page}]]\n{p.text}"
    for p in pages if p.page == 2
)

user = (
    "Przeanalizuj fragment dokumentu. Wyodrębnij wyraźnie "
    "sformułowane cele programu, problemy mieszkaniowe i działania "
    "gminy. Cytaty dowodowe muszą być dosłowne.\n\n"
    "<dokument>\n"
    + text
    + "\n</dokument>"
)

print("Wysyłam pierwsze 4 strony do modelu...", flush=True)

data = call_model(
    make_client(),
    cfg["llm"]["model_extract"],
    user,
    S.inline_schema(S.HousingItems),
    max_tokens=cfg["llm"]["max_tokens"],
    temperature=cfg["llm"].get("temperature"),
)

print("Cele:", len(data.get("goals", [])))
print("Problemy:", len(data.get("problems", [])))
print("Działania:", len(data.get("actions", [])))
print("Przykładowe cele:")
print(json.dumps(data.get("goals", [])[:3], ensure_ascii=False, indent=2))
