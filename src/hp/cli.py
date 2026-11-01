"""Interfejs wiersza poleceń:  python -m hp.cli <etap> [opcje]
Etapy: inventory | ingest | metadata | segment | cytaty | extract | validate | aggregate | analyze | report | codebook
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from . import aggregate as A, analysis as AN, export_codebook, ingest as I, metadata as M, segment as G, summarize as SM, validate as V


def cfg_load(path="config.yaml") -> dict:
    return yaml.safe_load(open(path, encoding="utf-8"))


def docs_from_registry(cfg) -> pd.DataFrame:
    return pd.read_csv(cfg["paths"]["registry"], dtype={"city_id": str})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hp")
    ap.add_argument("stage"); ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--doc", help="ogranicz do jednego doc_id"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--k", type=int, default=0, help="liczba typów (analyze); 0 = tylko skan k")
    a = ap.parse_args(argv)
    cfg = cfg_load(a.config); P = cfg["paths"]
    reg = docs_from_registry(cfg) if Path(P["registry"]).exists() else pd.DataFrame()
    if a.doc and len(reg):
        reg = reg[reg.doc_id == a.doc]

    if a.stage == "inventory":                               # rejestr startowy z plików PDF
        rows = [dict(doc_id=p.stem, file=p.name, doc_type="WPGMZ" if p.stem.upper().startswith("WPGMZ") else "SR",
                     sha256=I.sha256(p), city_id="", city="", voivodeship="", source_url="", notes="") for p in sorted(Path(P["raw"]).glob("*.pdf"))]
        pd.DataFrame(rows).to_csv(P["registry"], index=False); print(f"rejestr: {len(rows)} dokumentów -> {P['registry']} (uzupełnij city_id/TERYT)")
    elif a.stage == "ingest":
        reports = []
        for r in reg.itertuples():
            rep = I.ingest_document(Path(P["raw"]) / r.file, r.doc_id, P["interim"], ocr=cfg["ocr"]["enabled"], min_usable_chars=cfg["ocr"]["min_usable_chars"],
                                    lang=cfg["ocr"]["lang"], dpi=cfg["ocr"]["dpi"], tessdata=cfg["ocr"]["tessdata_prefix"])
            reports.append(rep); print(rep["doc_id"], rep["n_pages"], "stron, OCR:", rep["n_ocr_pages"], "needs_review:", rep["needs_review"])
        pd.DataFrame(reports).to_csv(Path(P["interim"]) / "_ingest_report.csv", index=False)
    elif a.stage in ("metadata", "segment"):
        out = []
        for r in reg.itertuples():
            pages = I.load_pages(r.doc_id, P["interim"])
            if a.stage == "metadata":
                out.append({"doc_id": r.doc_id, **{k: (";".join(v) if isinstance(v, list) else v) for k, v in M.extract_metadata([p.text for p in pages], r.doc_type).items()}})
            elif r.doc_type == "WPGMZ":
                out.append({"doc_id": r.doc_id, **G.segmentation_report(G.segment_wpgmz(pages))})
            else:
                ps = G.retrieve_passages(pages, cfg["retrieval"]["min_score"], cfg["retrieval"]["context_blocks"], cfg["retrieval"]["max_chars_per_doc"])
                out.append({"doc_id": r.doc_id, "n_passages": len(ps), "chars": sum(len(p.text) for p in ps)})
        pd.DataFrame(out).to_csv(Path(P["interim"]) / f"_{a.stage}.csv", index=False); print(pd.DataFrame(out).to_string())
    elif a.stage == "extract":
        from .extract_llm import make_client, run_document
        client = make_client()
        for r in reg.itertuples():
            pages = I.load_pages(r.doc_id, P["interim"])
            md = M.extract_metadata([p.text for p in pages], r.doc_type)
            secs = G.segment_wpgmz(pages) if r.doc_type == "WPGMZ" else None
            pas = G.retrieve_passages(pages, cfg["retrieval"]["min_score"], cfg["retrieval"]["context_blocks"], cfg["retrieval"]["max_chars_per_doc"]) if r.doc_type == "SR" else None
            run_document(client, cfg["llm"], r.doc_id, r.doc_type, pages, secs, pas, md, P["extracted"], a.force); print("ok", r.doc_id)
    elif a.stage == "validate":
        flags = [f for rec in A.load_records(P["extracted"]) for f in V.validate_record(rec)]
        pd.DataFrame(flags).to_csv(Path(P["outputs"]) / "validation_flags.csv", index=False); print(len(flags), "flag")
    elif a.stage == "aggregate":
        ext = pd.read_csv(Path(P["external"]) / "bdl.csv", dtype={"city_id": str}) if (Path(P["external"]) / "bdl.csv").exists() else None
        T = A.build_tables(A.load_records(P["extracted"]), reg, ext)
        T["city_indices"] = A.city_item_indices(T["docs"], T["problems"], T["actions"], T["goals"])
        T["alignment"] = A.alignment(T["problems"], T["actions"])
        for k, df in T.items():
            df.to_csv(Path(P["outputs"]) / f"{k}.csv", index=False)
        print({k: df.shape for k, df in T.items()})
    elif a.stage == "analyze":
        docs = pd.read_csv(Path(P["outputs"]) / "docs.csv", dtype={"city_id": str}); idx = pd.read_csv(Path(P["outputs"]) / "city_indices.csv", dtype={"city_id": str})
        w = docs[docs.doc_type == "WPGMZ"].merge(idx, on="city_id", how="left")
        num = [c for c in w.columns if c.startswith("idx_")] + ["n_instruments", "mean_specificity", "n_problem_categories"]
        cat = [c for c in ("rent__rent_target", "sales__sales_policy", "mgmt__manager_type") if c in w]
        D = AN.gower_distance(w, [c for c in num if c in w], cat)
        scan = AN.scan_k(D); scan.to_csv(Path(P["outputs"]) / "typology_scan_k.csv", index=False); print(scan)
        if a.k:
            lab = AN.cluster_labels(D, a.k); w["type"] = lab
            w[["doc_id", "city_id", "type"]].to_csv(Path(P["outputs"]) / "typology_assignment.csv", index=False)
            AN.profile(w, lab, [c for c in num if c in w], cat).to_csv(Path(P["outputs"]) / "typology_profile.csv")
            AN.heatmap(w, lab, [c for c in num if c in w], str(Path(P["outputs"]) / "typology_heatmap.png"))
    elif a.stage == "report":
        recs = A.load_records(P["extracted"])
        (Path(P["outputs"]) / "streszczenia.md").write_text("\n\n---\n\n".join(SM.card_markdown(r) for r in recs), encoding="utf-8"); print(len(recs), "kart")
    elif a.stage == "cytaty":                                # czytnik: dosłowne cytaty + ocena „działań własnych” (bez modelu językowego)
        from . import reader
        from .aggregate import city_key_from_doc_id
        rows, sums, metas = [], [], {}
        for r in reg.itertuples():
            pages = I.load_pages(r.doc_id, P["interim"])
            city = (getattr(r, "city", "") if isinstance(getattr(r, "city", ""), str) else "") or city_key_from_doc_id(r.doc_id)
            rr, ss = reader.read_document(r.doc_id, r.doc_type, pages, city)
            rows += rr; sums.append(ss); metas[r.doc_id] = M.extract_metadata([p.text for p in pages], r.doc_type)
            print(f"{r.doc_id}: {len(rr)} cytatów (A={ss['poziom_A']}, B={ss['poziom_B']}, C={ss['poziom_C']})")
        from . import card as K
        crow = []
        for r in reg.itertuples():
            pages = I.load_pages(r.doc_id, P["interim"])
            city = (getattr(r, "city", "") if isinstance(getattr(r, "city", ""), str) else "") or city_key_from_doc_id(r.doc_id)
            crow += K.answer_questions(r.doc_id, r.doc_type, city, pages)
        out = reader.export_xlsx(rows, sums, Path(P["outputs"]) / "cytaty.xlsx", metas)
        K.append_sheets(out, crow)
        pd.DataFrame(rows).to_csv(Path(P["outputs"]) / "cytaty.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(crow).to_csv(Path(P["outputs"]) / "karta_cytaty.csv", index=False, encoding="utf-8-sig"); print("->", out)
    elif a.stage == "codebook":
        print(export_codebook.export())
    else:
        ap.error("nieznany etap")


if __name__ == "__main__":
    main()
