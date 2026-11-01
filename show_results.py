"""Podgląd wyniku ekstrakcji jednego dokumentu:  python show_results.py [doc_id]"""
import json, sys
from pathlib import Path

doc_id = sys.argv[1] if len(sys.argv) > 1 else "WPGMZ_Gdynia_2022-2026"
f = Path("data/extracted") / f"{doc_id}.json"
r = json.loads(f.read_text(encoding="utf-8"))
it, au, v = r["items"], r["audit"], r["versions"]
print(f"{doc_id}\nmodel: {v['model']} | num_ctx: {v['num_ctx']} | przebieg: {v['run_date']}\n")
for kind, label in (("problems", "PROBLEMY"), ("actions", "DZIAŁANIA"), ("goals", "CELE")):
    items = it.get(kind, [])
    low = sum(1 for x in items if x.get("low_confidence"))
    print(f"=== {label}: {len(items)}" + (f"  (z tego niska pewność '?': {low})" if low else ""))
    for x in items:
        code = x.get("category") or x.get("instrument") or x.get("level")
        mark = "?" if x.get("low_confidence") else " "
        print(f"{mark} {code:<22} s.{x['evidence']['page']:<3} | {x['evidence']['quote'][:100]}" + (f"  [{', '.join(x['flags'])}]" if x.get("flags") else ""))
print("\n=== KONTROLA JAKOŚCI")
print(f"  cytaty zweryfikowane w tekście: {au.get('share_verified')}")
print(f"  pozycje odrzucone (cytatu nie ma w dokumencie): {len(au.get('items_rejected', []))}")
for x in au.get("items_rejected", [])[:12]:
    print("     -", x["kind"], "|", x.get("reason", ""), "|", x["quote"][:80])
print(f"  fragmenty, gdzie słownik widzi problem, a model nic nie zwrócił: {len(au.get('possible_misses', []))}")
for x in au.get("possible_misses", [])[:8]:
    print("     - strony", x["pages"], "|", ", ".join(x["categories"]))
print(f"  błędy wywołań modelu: {len(au.get('llm_errors', []))}")
for k, st in (au.get("candidate_stats") or {}).items():
    print(f"  tryb kandydatów [{k}]: zdań do klasyfikacji={st['candidates']}, przyjęte={st['accepted']}, wywołań modelu={st['batches']}")
