"""Testy całego łańcucha bez API: python -m pytest tests -q  (uruchom z katalogu głównego; wymaga data/interim po etapie ingest)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src")); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pandas as pd
import pytest

from hp import aggregate as A, analysis as AN, metadata as M, summarize as SM, validate as V
from hp.extract_llm import verify_evidence
from hp.ingest import load_pages
from hp.segment import fold_pl, classify_heading

try:
    import fixtures
    HAVE = os.path.exists("data/interim/WPGMZ_Gdynia_2022-2026.pages.jsonl")
except Exception:
    HAVE = False
need_pages = pytest.mark.skipif(not HAVE, reason="uruchom najpierw etap ingest na przykładowych PDF-ach")


def test_invalid_calendar_date_is_not_silently_fixed():
    assert M.parse_date("stan na dzień 31.09.2021 r.") is None          # taka data jest w WPGMZ Gdyni
    assert M.parse_date("z dnia 27 października 2021 r.") == "2021-10-27"


def test_metadata_header():
    txt = "UCHWAŁA NR XXXVI/43/22 RADY MIASTA BIAŁA PODLASKA z dnia 29 kwietnia 2022 r. w sprawie zmiany uchwały na lata 2021-2025"
    md = M.extract_metadata([txt], "WPGMZ")
    assert md["resolution_number"] == "XXXVI/43/22" and md["adoption_date"] == "2022-04-29"
    assert (md["period_start"], md["period_end"]) == (2021, 2025) and md["is_amendment"]


def test_heading_classification_survives_ocr_diacritics():
    assert classify_heading("Zródła finansowania gospodarki komunalnym zasobem") == "E6"
    assert fold_pl("Źródła") == "Zrodla"


@need_pages
def test_fixture_chain_verify_validate_aggregate_summarize():
    recs = [fixtures.gdynia(), fixtures.olsztyn()]
    for rec in recs:
        pages = load_pages(rec["doc_id"], "data/interim")
        rec["audit"] = verify_evidence(rec, pages)
        assert rec["audit"]["share_verified"] >= 0.9, rec["audit"]["unverified"]
        flags = V.validate_record(rec)
        assert not [f for f in flags if f["level"] == "error"], flags
    reg = pd.DataFrame([dict(doc_id=r["doc_id"], city_id=c) for r, c in zip(recs, ["2262011", "2862011"])])
    T = A.build_tables(recs, reg, pd.DataFrame(dict(city_id=["2262011", "2862011"], population=[243000, 170000])))
    d = T["docs"].set_index("doc_id")
    assert d.loc["WPGMZ_Gdynia_2022-2026", "stock__units_total"] == 5254
    assert round(d.loc["WPGMZ_Olsztyn_2022-2026", "idx_stock_change_pct"], 1) == -12.1
    assert d.loc["WPGMZ_Gdynia_2022-2026", "sales__sales_policy"] == "halted"
    al = A.alignment(T["problems"], T["actions"])
    g = al.set_index("city_id").loc["2262011"]                                          # Gdynia (fixture): P05←I02, P04←I07, P02 bez działania
    assert round(g.alignment_index, 3) == 0.667 and g.orphan_problems == "P02"
    assert "WPGMZ_Gdynia" in SM.card_markdown(recs[0])


def test_value_without_found_is_flagged():
    rec = dict(doc_id="x", doc_type="WPGMZ", metadata={}, blocks={"b": {"s": {"f": dict(value=5, status="not_present", evidence=[])}}})
    assert any(f["code"] == "value_without_found" for f in V.validate_record(rec))


def test_typology_runs_and_recovers_two_planted_groups():
    rng = np.random.default_rng(0)
    n = 66
    g = np.r_[np.zeros(33), np.ones(33)].astype(int)
    df = pd.DataFrame(dict(growth=rng.normal(g * 8, 2), sales=rng.normal((1 - g) * 3, 0.5), spec=rng.normal(2 + g, 0.3),
                           model=np.where(g == 1, "tbs", "gmina"), noise=rng.normal(size=n)))
    df.loc[::9, "sales"] = np.nan                                                  # braki danych
    D = AN.gower_distance(df, ["growth", "sales", "spec"], ["model"])
    scan = AN.scan_k(D, range(2, 5), n_boot=30)
    assert scan.sort_values("silhouette").iloc[-1].k == 2
    lab = AN.cluster_labels(D, 2)
    from sklearn.metrics import adjusted_rand_score
    assert adjusted_rand_score(g, lab) > 0.9
