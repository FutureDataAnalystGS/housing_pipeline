"""Ocena jakości modelu względem ręcznego wzorca (tests/fixtures.py: Gdynia, Olsztyn).

Uruchomienie:  PYTHONPATH=src:tests python -m hp.evaluate            (czyta data/extracted/<doc_id>.json)
To jest odpowiedź na pytanie „na ile wiarygodny jest model lokalny”: zmierz go, zamiast zakładać.
Wzorzec jest mały i niepełny (kilka pozycji na dokument), więc:
  * RECALL pozycji względem wzorca jest wiarygodną miarą,
  * PRECYZJA jest tylko dolnym oszacowaniem (model może znaleźć poprawne pozycje, których wzorzec nie ma) — „extra” przejrzyj ręcznie.
Dopisuj kolejne dokumenty do wzorca (ręcznie kodowane), a miara będzie coraz lepsza.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _facts(rec: dict) -> dict[str, float]:
    out: dict[str, float] = {}

    def walk(node, path):
        if isinstance(node, dict):
            if "status" in node and "value" in node:
                if node.get("status") == "found" and node.get("value") is not None:
                    out[path] = node["value"]
            else:
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else k)
    walk(rec.get("blocks") or {}, "")
    return out


def compare(pred: dict, gold: dict, tol: float = 0.005) -> dict:
    gf, pf = _facts(gold), _facts(pred)
    hit = sum(1 for k, v in gf.items() if k in pf and (abs(pf[k] - v) <= tol * max(1, abs(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else pf[k] == v))
    wrong = [k for k, v in gf.items() if k in pf and pf[k] != v]
    res = dict(facts_gold=len(gf), facts_exact=hit, facts_missing=len([k for k in gf if k not in pf]), facts_wrong=wrong,
               facts_extra=len([k for k in pf if k not in gf]))
    for kind, field in (("problems", "category"), ("actions", "instrument"), ("goals", "level")):
        g = {x[field] for x in (gold.get("items") or {}).get(kind, [])}
        p = [x[field] for x in (pred.get("items") or {}).get(kind, [])]
        ps = set(p)
        res[f"{kind}_gold"] = sorted(g)
        res[f"{kind}_recall"] = round(len(g & ps) / len(g), 2) if g else None
        res[f"{kind}_found_total"] = len(p)
        res[f"{kind}_extra_codes"] = sorted(ps - g)
    return res


def main(extracted_dir: str = "data/extracted"):
    import fixtures
    rows = []
    for fn in (fixtures.gdynia, fixtures.olsztyn):
        gold = fn()
        f = Path(extracted_dir) / f"{gold['doc_id']}.json"
        if not f.exists():
            print(f"brak {f} — najpierw: python -m hp.cli extract --doc {gold['doc_id']}")
            continue
        pred = json.loads(f.read_text(encoding="utf-8"))
        r = compare(pred, gold)
        r["doc_id"] = gold["doc_id"]
        r["share_verified"] = (pred.get("audit") or {}).get("share_verified")
        r["items_rejected"] = len((pred.get("audit") or {}).get("items_rejected", []))
        rows.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    return rows


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
