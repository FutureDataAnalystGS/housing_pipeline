"""Etap 5a. Automatyczne kontrole spójności wyników (flagi trafiają do kolejki ręcznej weryfikacji)."""
from __future__ import annotations

from datetime import date


def _v(block: dict | None, field: str):
    """Wartość liczbowa pola NumFact (albo None) — tylko ze statusem found."""
    if not block:
        return None
    f = block.get(field) or {}
    return f.get("value") if f.get("status", "found") == "found" else None


def validate_record(rec: dict, tol: float = 0.02) -> list[dict]:
    flags: list[dict] = []

    def flag(code, msg, level="warn"):
        flags.append(dict(doc_id=rec["doc_id"], code=code, level=level, message=msg))

    md = rec.get("metadata", {})
    for k in ("adoption_date", "publication_date"):
        if md.get(k):
            try:
                date.fromisoformat(md[k])
            except ValueError:
                flag("bad_date", f"{k}={md[k]} nie jest poprawną datą", "error")
    if md.get("period_start") and md.get("period_end") and md["period_end"] < md["period_start"]:
        flag("bad_period", "koniec okresu < początek", "error")
    if md.get("adoption_date") and md.get("period_start") and int(md["adoption_date"][:4]) > md["period_start"] + 1:
        flag("adopted_late", "uchwała przyjęta ponad rok po początku okresu — sprawdź, czy to nowelizacja", "info")

    b = rec.get("blocks", {})
    st = (b.get("stock_condition_needs") or {}).get("stock")
    fc = (b.get("forecast_sales") or {}).get("forecast")
    if st:
        parts = [_v(st, k) for k in ("units_gmina_100pct", "units_wspolnoty", "units_other_owners")]
        tot = _v(st, "units_total")
        if tot and all(p is not None for p in parts) and abs(sum(parts) - tot) > max(1, tol * tot):
            flag("stock_sum_mismatch", f"części zasobu ({sum(parts):.0f}) ≠ razem ({tot:.0f})")
        if tot is not None and not (100 <= tot <= 60000):
            flag("stock_out_of_range", f"units_total={tot} poza typowym zakresem dla miasta na prawach powiatu")
        a = _v(st, "area_total_m2")
        if a and tot and not (15 <= a / tot <= 120):
            flag("area_per_unit_implausible", f"{a/tot:.0f} m2 na lokal")
    if fc:
        s0, s1 = _v(fc, "stock_start_units"), _v(fc, "stock_end_units")
        parts = {k: _v(fc, k) for k in ("planned_new_units_total", "planned_purchases_units_total",
                                         "planned_demolitions_units_total", "planned_sales_units_total")}
        if None not in (s0, s1) and all(v is not None for v in parts.values()):
            exp = s0 + parts["planned_new_units_total"] + parts["planned_purchases_units_total"] \
                - parts["planned_demolitions_units_total"] - parts["planned_sales_units_total"]
            if abs(exp - s1) > max(5, tol * s0):
                flag("forecast_balance", f"bilans prognozy ({exp:.0f}) ≠ stan końcowy ({s1:.0f}); możliwy ruch ludności/inne korekty", "info")
        if st and s0 and _v(st, "units_total") and abs(s0 - _v(st, "units_total")) / s0 > 0.10:
            flag("stock_vs_forecast_start", "stan zasobu w W1 różni się od startu prognozy >10% (inne daty lub definicje)")
    for blk, field in (("rent_mgmt", "rent"),):
        r = (b.get(blk) or {}).get(field)
        p = _v(r, "social_rent_max_pct_of_lowest")
        if p is not None and not (0 < p <= 100):
            flag("pct_out_of_range", "social_rent_max_pct_of_lowest poza 0–100")
    for bname, blk in (rec.get("blocks") or {}).items():
        for sub, d in (blk or {}).items():
            for field, f in (d or {}).items():
                if isinstance(f, dict) and "status" in f and f.get("value") is not None and f["status"] != "found":
                    flag("value_without_found", f"{bname}.{sub}.{field}: wartość przy statusie {f['status']}")
                if isinstance(f, dict) and f.get("status") == "found" and f.get("value") is not None and not f.get("evidence"):
                    flag("found_without_evidence", f"{bname}.{sub}.{field}: brak dowodu", "error")
    au = rec.get("audit") or {}
    if au.get("share_verified") is not None and au["share_verified"] < 0.9:
        flag("evidence_unverified", f"tylko {au['share_verified']:.0%} cytatów zweryfikowanych w tekście", "error")
    for n in au.get("numbers_unsupported", []):
        flag("number_not_in_quote", f"{n['path']}={n['value']}: cyfry wartości nie występują w cytacie (status zmieniono na unclear)", "error")
    if au.get("items_rejected"):
        flag("items_rejected", f"{len(au['items_rejected'])} pozycji odrzuconych (cytat nie występuje w dokumencie)", "warn")
    if au.get("possible_misses"):
        flag("possible_misses", f"{len(au['possible_misses'])} fragmentów, gdzie słownik widzi problem, a model nic nie zwrócił — przejrzyj", "warn")
    if au.get("llm_errors"):
        flag("llm_errors", f"{len(au['llm_errors'])} wywołań modelu nie powiodło się (ucięta odpowiedź/za długi prompt)", "error")
    if rec.get("versions", {}).get("segmentation_fallback"):
        flag("segmentation_fallback", "nie rozpoznano ≥5 elementów ustawowych — kodowano z całego dokumentu", "info")
    return flags
