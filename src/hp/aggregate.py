"""Etap 6. Agregacja: rekordy JSON -> tabele analityczne (szerokie i długie) + wskaźniki pochodne."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .taxonomy import CROSSWALK, INSTRUMENTS


def _flat_block(prefix: str, block: dict | None, row: dict) -> None:
    for field, val in (block or {}).items():
        key = f"{prefix}__{field}"
        if isinstance(val, dict) and "status" in val:
            row[key] = val.get("value")
            row[key + "__status"] = val.get("status")
            ev = val.get("evidence") or []
            row[key + "__page"] = ev[0].get("page") if ev else None
        elif isinstance(val, list):
            if val and isinstance(val[0], dict):          # lista Project
                row[f"{key}_n"] = len(val)
                row[f"{key}_units"] = sum((v.get("units") or 0) for v in val)
            else:
                row[key] = ";".join(str(x) for x in val)
        elif isinstance(val, dict):
            _flat_block(key, val, row)


def specificity(a: dict) -> int:
    if not a.get("named_instrument", True):
        return 1
    return 2 + int(bool(a.get("has_target_value"))) + int(bool(a.get("has_budget_or_source"))) + int(bool(a.get("has_deadline_or_owner")))


def load_records(extracted_dir: str | Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(extracted_dir).glob("*.json"))]


def build_tables(records: list[dict], registry: pd.DataFrame, external: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    wide, prob, goal, act = [], [], [], []
    for rec in records:
        row = {"doc_id": rec["doc_id"], "doc_type": rec["doc_type"], **{f"meta__{k}": v for k, v in rec["metadata"].items() if k != "needs_review"}}
        for name, blk in (rec.get("blocks") or {}).items():
            if blk:
                for sub, d in blk.items():
                    _flat_block(sub, d, row)
        it = rec.get("items") or {}
        row["items__relevant"] = it.get("relevant")
        for p in it.get("problems", []):
            prob.append(dict(doc_id=rec["doc_id"], doc_type=rec["doc_type"], category=p["category"], severity=p["severity"],
                             quantified=p.get("quantified"), statement=p["statement"], page=(p.get("evidence") or {}).get("page")))
        for g in it.get("goals", []):
            goal.append(dict(doc_id=rec["doc_id"], doc_type=rec["doc_type"], level=g["level"], dimension=g["dimension"],
                             statement=g["statement"], page=(g.get("evidence") or {}).get("page")))
        for a in it.get("actions", []):
            act.append(dict(doc_id=rec["doc_id"], doc_type=rec["doc_type"], instrument=a["instrument"],
                            family=INSTRUMENTS.get(a["instrument"], {}).get("family"), stance=a.get("stance"), status=a["status"],
                            specificity=specificity(a), link_explicit=a.get("link_explicit"),
                            addresses=";".join(a.get("addresses_problems", [])), description=a["description"],
                            page=(a.get("evidence") or {}).get("page")))
        au = rec.get("audit") or {}
        row["audit__share_verified"] = au.get("share_verified")
        wide.append(row)
    docs = pd.DataFrame(wide).merge(registry, on=["doc_id"], how="left", suffixes=("", "_reg"))

    problems = pd.DataFrame(prob, columns=[
        "doc_id", "doc_type", "category", "severity",
        "quantified", "statement", "page"
    ])
    goals = pd.DataFrame(goal, columns=[
        "doc_id", "doc_type", "level", "dimension", "statement", "page"
    ])
    actions = pd.DataFrame(act, columns=[
        "doc_id", "doc_type", "instrument", "family", "stance",
        "status", "specificity", "link_explicit", "addresses",
        "description", "page"
    ])

    doc_city = docs.drop_duplicates("doc_id").set_index("doc_id")["city_id"]
    for df in (problems, goals, actions):
        df.insert(1, "city_id", df["doc_id"].map(doc_city))

    docs = add_indices(docs, external)
    return dict(docs=docs, problems=problems, goals=goals, actions=actions)


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)


def add_indices(docs: pd.DataFrame, external: pd.DataFrame | None) -> pd.DataFrame:
    d = docs.copy()
    if external is not None and "city_id" in d:
        d = d.merge(external, on="city_id", how="left")
    tot, s0, s1 = _num(d, "stock__units_total"), _num(d, "forecast__stock_start_units"), _num(d, "forecast__stock_end_units")
    years = (_num(d, "forecast__forecast_end_year") - _num(d, "forecast__forecast_start_year")).clip(lower=1)
    pop = _num(d, "population")
    d["idx_units_per_1000_inh"] = tot / pop * 1000
    d["idx_share_gmina_100pct"] = _num(d, "stock__units_gmina_100pct") / tot
    d["idx_share_wspolnoty"] = _num(d, "stock__units_wspolnoty") / tot
    d["idx_share_social_temp"] = (_num(d, "stock__units_social_rent").fillna(0) + _num(d, "stock__units_temporary").fillna(0)) / tot
    d["idx_stock_change_pct"] = (s1 - s0) / s0 * 100
    d["idx_new_units_per_1000_stock"] = _num(d, "forecast__planned_new_units_total") / s0 * 1000
    d["idx_sales_pct_stock_per_year"] = _num(d, "forecast__planned_sales_units_total") / s0 / years * 100
    d["idx_repairs_pln_per_unit_per_year"] = _num(d, "repairs__outlays_repairs_total_pln") / tot / years
    d["idx_modernization_pln_per_unit_per_year"] = _num(d, "repairs__outlays_modernization_total_pln") / tot / years
    d["idx_cost_coverage"] = _num(d, "finance__rent_revenue_y1_pln") / _num(d, "finance__total_costs_y1_pln")
    d["idx_pct_coal_heating"] = _num(d, "condition__units_coal_heating") / tot
    return d


def city_item_indices(docs: pd.DataFrame, problems: pd.DataFrame, actions: pd.DataFrame, goals: pd.DataFrame) -> pd.DataFrame:
    """Wskaźniki na poziomie miasta z pozycji kodowanych (szerokość, intensywność, konkretność)."""
    out = docs[["city_id"]].drop_duplicates().set_index("city_id")
    if len(problems):
        out["n_problem_categories"] = problems.groupby("city_id")["category"].nunique()
        out["n_problems_key"] = problems[problems.severity == "key"].groupby("city_id").size()
    if len(actions):
        a = actions[actions.status.isin(["existing", "planned"])]
        out["n_instruments"] = a.groupby("city_id")["instrument"].nunique()
        out["n_instrument_families"] = a.groupby("city_id")["family"].nunique()
        out["mean_specificity"] = a.groupby("city_id")["specificity"].mean()
        out["share_actions_planned_new"] = a.assign(n=(a.status == "planned")).groupby("city_id")["n"].mean()
        out["share_actions_link_explicit"] = actions.assign(l=actions.link_explicit.fillna(False).astype(bool)).groupby("city_id")["l"].mean()
    if len(goals):
        out["n_goals"] = goals.groupby("city_id").size()
    return out.fillna({c: 0 for c in out.columns if c.startswith("n_")}).reset_index()


def alignment(problems: pd.DataFrame, actions: pd.DataFrame, p_types=("SR", "WPGMZ"), a_types=("SR", "WPGMZ")) -> pd.DataFrame:
    """RQ4. Indeks pokrycia diagnozy działaniami: odsetek zdiagnozowanych kategorii problemów (bez P99),
    dla których istnieje ≥1 działanie z listy CROSSWALK. Zwraca także „osierocone” problemy i działania."""
    rows = []
    cities = sorted(set(problems.get("city_id", [])) | set(actions.get("city_id", [])))
    for c in cities:
        P = set(problems[(problems.city_id == c) & problems.doc_type.isin(p_types)].category) - {"P99"}
        sub = actions[(actions.city_id == c) & actions.doc_type.isin(a_types) & actions.status.isin(["existing", "planned"])]
        A = set(sub.instrument)
        covered = {p for p in P if set(CROSSWALK.get(p, [])) & A}
        relevant_instr = set().union(*[set(CROSSWALK.get(p, [])) for p in P]) if P else set()
        rows.append(dict(city_id=c, n_problems=len(P), n_covered=len(covered),
                         alignment_index=len(covered) / len(P) if P else np.nan,
                         orphan_problems=";".join(sorted(P - covered)),
                         n_actions_instr=len(A), share_actions_linked_to_diagnosis=len(A & relevant_instr) / len(A) if A else np.nan,
                         orphan_actions=";".join(sorted(A - relevant_instr))))
    return pd.DataFrame(rows)
