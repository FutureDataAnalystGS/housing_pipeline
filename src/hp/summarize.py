"""Etap 8. Streszczenia dokumentów. Zawsze z ZWERYFIKOWANYCH pól JSON (nie z surowego tekstu), co ogranicza halucynacje."""
from __future__ import annotations

import json

from .taxonomy import INSTRUMENTS, PROBLEMS


def _fmt(f: dict | None, unit: str = "") -> str:
    if not f or f.get("status") != "found" or f.get("value") is None:
        return "brak danych"
    v = f["value"]
    return f"{v:,.0f}".replace(",", " ") + (f" {unit}" if unit else "")


def card_markdown(rec: dict) -> str:
    md, b, it = rec["metadata"], rec.get("blocks") or {}, rec.get("items") or {}
    typ = "Wieloletni program gospodarowania mieszkaniowym zasobem gminy" if rec["doc_type"] == "WPGMZ" else "Strategia rozwoju"
    lines = [f"### {rec['doc_id']}", f"**{typ}.** Uchwała {md.get('resolution_number') or 'brak danych'} z {md.get('adoption_date') or 'brak daty'}; "
             f"okres {md.get('period_start') or '?'}–{md.get('period_end') or '?'}" + (" (nowelizacja)" if md.get("is_amendment") else "") + "."]
    if rec["doc_type"] == "WPGMZ":
        s = (b.get("stock_condition_needs") or {}).get("stock")
        f = (b.get("forecast_sales") or {}).get("forecast")
        lines.append(f"Zasób: {_fmt((s or {}).get('units_total'), 'lokali')} ({_fmt((s or {}).get('area_total_m2'), 'm²')}); "
                     f"prognoza: {_fmt((f or {}).get('stock_start_units'))} → {_fmt((f or {}).get('stock_end_units'))} lokali; "
                     f"nowe lokale: {_fmt((f or {}).get('planned_new_units_total'))}; sprzedaż: {_fmt((f or {}).get('planned_sales_units_total'))}.")
    else:
        fr = b.get("strategy_frame") or {}
        lines.append(f"Miejsce mieszkalnictwa w strategii: {(fr.get('integration_level') or {}).get('value') or 'brak danych'}.")
    probs = sorted(it.get("problems", []), key=lambda p: {"key": 0, "notable": 1, "mention": 2}[p["severity"]])[:4]
    if probs:
        lines.append("Główne problemy: " + "; ".join(f"{PROBLEMS[p['category']]['name']} ({p['severity']}, s. {(p.get('evidence') or {}).get('page')})" for p in probs) + ".")
    acts = [a for a in it.get("actions", []) if a["status"] in ("existing", "planned")]
    if acts:
        top = sorted(acts, key=lambda a: -(int(a.get("has_target_value", False)) + int(a.get("has_budget_or_source", False)) + int(a.get("has_deadline_or_owner", False))))[:5]
        lines.append("Kluczowe działania: " + "; ".join(INSTRUMENTS[a["instrument"]]["name"] for a in top) + ".")
    au = rec.get("audit") or {}
    if au.get("share_verified") is not None:
        lines.append(f"_Jakość kodowania: {au['share_verified']:.0%} cytatów zweryfikowanych programowo._")
    return "\n\n".join(lines)


def llm_summary(client, cfg: dict, rec: dict) -> str:
    from .extract_llm import call_model
    schema = {"type": "object", "properties": {"streszczenie": {"type": "string"}}, "required": ["streszczenie"]}
    it = rec.get("items") or {}
    payload = card_markdown(rec) + "\n\nProblemy: " + "; ".join(p["statement"] for p in it.get("problems", [])[:12]) + \
        "\nCele: " + "; ".join(g["statement"] for g in it.get("goals", [])[:10]) + \
        "\nDziałania: " + "; ".join(a["description"] for a in it.get("actions", [])[:14])
    payload = payload[:9000]
    user = ("Na podstawie WYŁĄCZNIE poniższych zakodowanych danych napisz streszczenie dokumentu (120–180 słów, po polsku, styl naukowy, "
            "bez ocen własnych): typ i okres dokumentu, skala i stan zasobu, główne problemy, cele i instrumenty, konkretność i finansowanie. "
            "Nie dodawaj informacji spoza danych.\n\n" + payload)
    out = call_model(client, cfg["model_summary"], user, schema, max_tokens=800, temperature=cfg.get("temperature"),
                     system="Jesteś asystentem badawczym. Piszesz zwięzłe, rzeczowe streszczenia w języku polskim.")
    return out["streszczenie"]
