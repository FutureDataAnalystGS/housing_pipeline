"""Czytnik dokumentów: lista DOSŁOWNYCH cytatów pogrupowanych tematycznie (bez modelu językowego).

Cel: badaczka sama czyta i interpretuje, a program (1) znajduje zdania o problemach, zasobie i jego stanie, finansach, celach i działaniach,
(2) podaje stronę i słowa-klucze, które zdecydowały o oznaczeniu, (3) ocenia, czy dokument wskazuje działania „własne” gminy.
Każdy cytat jest zdaniem/akapitem skopiowanym z PDF-a (po sklejeniu łamania wierszy) — niczego nie parafrazujemy ani nie generujemy.
Znaczniki tematów to reguły słownikowe (lexicon.py): są jawne, powtarzalne i łatwe do poprawienia, ale mają ograniczoną dokładność
(zdanie może dostać kilka etykiet albo żadnej) — traktuj je jako pomoc w czytaniu, nie jako kodowanie ostateczne.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from . import candidates as C
from .ingest import Page
from .lexicon import _INSTR_FULL, _PROB_FULL, score as housing_score
from .taxonomy import INSTRUMENTS, POLICY_TIER, PROBLEMS, TIER_NAMES

_FIN = {
    "przychody (czynsze, wpływy)": re.compile(r"wpływ\w*\s+(?:czynsz|z\s+czynsz|ze\s+sprzeda|z\s+najmu)|przychod\w+|czynsz\w*\s+(?:pokryw|pokrywa)|dochod\w+\s+ze\s+sprzeda", re.I),
    "koszty i nakłady": re.compile(r"koszt\w+|wydatk\w+|nakład\w+|fundusz\w*\s+remontow", re.I),
    "zaległości i zadłużenie": re.compile(r"zaległo\w+|zadłuż\w+|ściągaln\w+|odszkodowan\w+", re.I),
    "dotacje i środki zewnętrzne": re.compile(r"dotacj\w+|dofinansowan\w+|\bBGK\b|Fundusz\w*\s+Dopłat|\bKPO\b|środk\w+\s+(?:zewnętrzn|budżet)|kredyt\w*|pożyczk\w+|budżet\w*\s+(?:gminy|miasta)", re.I),
}
_STOCK = {
    "zasób: wielkość": re.compile(r"zasób\w*\s+mieszkaniow\w*[^.]{0,80}\d|tworzy\s+[\d ]+\s*lokal|[\d]{1,3}(?:[ \u00a0]\d{3})+\s+lokal|\d+\s+lokal\w+|powierzchni\w*\s+użytkow\w+|\d+\s+budynk\w+", re.I),
    "zasób: struktura własności": re.compile(r"wspólnot\w+\s+mieszkaniow\w*|w\s+budynkach\s+(?:gminnych|stanowiących)|spółdziel\w+|innych\s+(?:właściciel|budynk)|Skarb\w*\s+Państwa", re.I),
    "zasób: stan i standard": re.compile(r"stan\w*\s+technicz\w+|przed\s+19\d\d|piec\w+|sutere\w+|\bWC\b|łazienk\w+|centraln\w+\s+ogrzewani\w+|wiek\w*\s+budynk|standard\w*", re.I),
}
_GOAL = re.compile(r"\bcel(?:e|em|ów|u|ach)?\b|priorytet\w*|kierunk\w+\s+(?:działań|rozwoju)", re.I)
_STRONG_ACT = re.compile(r"planuje|zakłada\s+się|przewiduje\s+się|podejmie|podejmowa\w+|dąży|będzie\s+dążyć|zostan\w+\s+(?:zrealiz|wykonan|przeprowadz)|kontynu\w+", re.I)
_VERDICT_CUE = re.compile(r"planuj|zakłada|przewiduj|podejm|dąży|dążyć|będzie|będą|zostan|zapewnia|zapewni|prowadz|realizuj|wynajmuj|finansuj|dofinansowuj|tworzy|utworz|"
                          r"\bbudow|rozwój|rozwijan|wspier|tworzeni|wspieran|zwiększ|powiększ|kontynu|wdraża|wdroże|realizacj|nabywa|zakup|pozyskuj|przekazuj|funkcjonuj|działa", re.I)
_NOMINAL = re.compile(r"tworzeni\w+|wdrażani\w+|wdraża\w+|kreowani\w+|\brozwój\w*|wspieran\w+|zaspokajani\w+", re.I)
_POLICY = re.compile(r"polityk\w+\s+mieszkaniow|potrzeb\w+\s+mieszkaniow|budownictw\w+\s+mieszkaniow|mieszkalnictw|instrument\w+", re.I)
_NEG = re.compile(r"\bnie\s+(?:planuje|przewiduje|będzie|prowadzi|realizuje|podejmuje)\b|\bbrak\s+(?:działań|planów)", re.I)
_STATUS_PL = {"existing": "istniejące/kontynuowane", "planned": "planowane", "conditional": "warunkowe"}
_STANCE_PL = {"restrict": "ograniczanie/wstrzymanie", "expand": "rozszerzanie", "maintain": "utrzymanie", "not_applicable": ""}


def _hits(patterns: dict, text: str) -> dict[str, list[str]]:
    out = {}
    for k, rx in patterns.items():
        m = rx.findall(text) if rx.groups == 0 else [x.group(0) for x in rx.finditer(text)]
        m = [x if isinstance(x, str) else x[0] for x in m]
        if m:
            out[k] = m
    return out


def tag_unit(u: C.Unit, doc_type: str) -> list[dict]:
    """Zwraca wiersze (jeden na parę zdanie × temat). Zdania z podstawą prawną/definicją pomijamy."""
    t = u.text
    if C._NOT_TEXT.search(t):
        return []
    if doc_type == "SR" and housing_score(t) < 1.0:
        return []
    table = C.is_table_like(t)
    typ = "tabela/kwoty" if table else "zdanie"
    rows: list[dict] = []

    def add(kat, temat, kw, **extra):
        rows.append(dict(strona=u.page, kategoria=kat, temat=temat, cytat=t, typ=typ, slowa_kluczowe=", ".join(dict.fromkeys(x.lower() for x in kw))[:120], **extra))

    if not table:
        ph = _hits(_PROB_FULL, t)
        if ph:
            for code, kw in ph.items():
                add("Problem", f"{code} {PROBLEMS[code]['name']}", kw)
        elif C._P_CUES.search(t):
            add("Problem", "P?? sygnał problemu (bez kategorii)", [m.group(0) for m in C._P_CUES.finditer(t)][:3])
        if _GOAL.search(t):
            add("Cel/priorytet", "cel lub priorytet", [m.group(0) for m in _GOAL.finditer(t)][:3])
    for temat, kw in _hits(_STOCK, t).items():
        add("Zasób i stan", temat, kw)
    for temat, kw in _hits(_FIN, t).items():
        add("Finanse", temat, kw)
    ih = _hits(_INSTR_FULL, t)
    if ih and (C._A_CUES.search(t) or table):
        neg = bool(_NEG.search(t))
        st, sn = C.act_status(t), C.act_stance(t)
        for code, kw in ih.items():
            add("Działanie", f"{code} {INSTRUMENTS[code]['name']}", kw, poziom=POLICY_TIER.get(code, ""),
                status=("zaprzeczone" if neg else _STATUS_PL[st]), kierunek=_STANCE_PL[sn], sygnal=("tak" if _VERDICT_CUE.search(t) else "nie"))
    elif not table and housing_score(t) >= 1.0 and (_STRONG_ACT.search(t) or (_NOMINAL.search(t) and _POLICY.search(t))):
        kw = [m.group(0) for m in _STRONG_ACT.finditer(t)] or [m.group(0) for m in _NOMINAL.finditer(t)]
        add("Działanie", "deklaracja ogólna (bez nazwanego instrumentu)", kw[:3], poziom="G",
            status=_STATUS_PL[C.act_status(t)], kierunek=_STANCE_PL[C.act_stance(t)], sygnal="tak")
    return rows


def read_document(doc_id: str, doc_type: str, pages: list[Page], city: str = "") -> tuple[list[dict], dict]:
    units = C.build_units(pages, max_chars=240 if doc_type == "SR" else 380)      # strategie: krótsze jednostki (wypunktowania, SWOT)
    rows: list[dict] = []
    for i, u in enumerate(units, 1):
        for r in tag_unit(u, doc_type):
            rows.append(dict(doc_id=doc_id, miasto=city, typ_dokumentu=doc_type, id_cytatu=i, **r))
    return rows, summarize(doc_id, doc_type, city, rows, pages)


def own_policy(rows: list[dict]) -> dict:
    """Ocena poziomów A/B/C: liczba cytatów o działaniach w poziomie, instrumenty i przykładowe cytaty (bez zaprzeczonych)."""
    res = {}
    for tier in ("A", "B", "C", "G"):
        sel = [r for r in rows if r["kategoria"] == "Działanie" and r.get("poziom") == tier and r.get("status") != "zaprzeczone" and r.get("sygnal") == "tak"]
        codes = Counter(r["temat"] for r in sel)
        seen, ex = set(), []
        for r in sorted(sel, key=lambda r: (r["typ"] != "zdanie", r["strona"])):
            if r["id_cytatu"] not in seen and len(ex) < 3:
                seen.add(r["id_cytatu"])
                ex.append(f"s.{r['strona']}: {r['cytat'][:220]}")
        res[tier] = dict(n=len({r["id_cytatu"] for r in sel}), instruments=dict(codes), examples=ex)
    return res


def summarize(doc_id, doc_type, city, rows, pages) -> dict:
    cnt = Counter(r["kategoria"] for r in rows)
    op = own_policy(rows)
    return dict(doc_id=doc_id, miasto=city, typ_dokumentu=doc_type, n_stron=len(pages), n_stron_OCR=sum(1 for p in pages if p.method == "ocr"),
                **{f"cytaty_{k}": cnt.get(k, 0) for k in ("Problem", "Zasób i stan", "Finanse", "Cel/priorytet", "Działanie")},
                **{f"poziom_{t}": op[t]["n"] for t in "ABCG"}, _own=op)


def city_verdict(doc_summaries: list[dict]) -> dict:
    """Łączy dokumenty jednego miasta (WPGMZ + strategia) w odpowiedź na pytanie o działania własne."""
    own = {t: dict(n=0, instruments=Counter(), examples=[]) for t in "ABCG"}
    for d in doc_summaries:
        for t in "ABCG":
            o = d["_own"][t]
            own[t]["n"] += o["n"]
            own[t]["instruments"].update(o["instruments"])
            own[t]["examples"] += [f"[{d['typ_dokumentu']}] {e}" for e in o["examples"]]
    a = own["A"]
    total = sum(d.get(f"cytaty_{k}", 0) for d in doc_summaries for k in ("Problem", "Zasób i stan", "Finanse", "Cel/priorytet", "Działanie"))
    verdict = ("TAK: dokumenty wskazują działania własne (poziom A)" if a["n"] >= 2 else
               "PRAWDOPODOBNIE: pojedyncza wzmianka (poziom A) — sprawdź cytat" if a["n"] == 1 else
               "OGÓLNA DEKLARACJA: dokumenty zapowiadają działania mieszkaniowe bez nazwanego instrumentu własnego (G) — przeczytaj cytaty" if own["G"]["n"] else
               "NIE w dokumentach: są cytaty o działaniach B/C, ale żadnego poziomu A" if (own["B"]["n"] + own["C"]["n"]) else
               "NIE w dokumentach: są cytaty o mieszkalnictwie (problemy, zasób), ale bez sygnału działań — przeczytaj je" if total else
               "BRAK DANYCH: nie znaleziono żadnych cytatów o mieszkalnictwie (dokument pusty, nieczytelny lub bez tego tematu)")
    return dict(werdykt=verdict, **{t: own[t] for t in "ABCG"})


# ------------------------------------------------------------------ eksport do Excela
def export_xlsx(rows: list[dict], summaries: list[dict], path: str | Path, metadata: dict[str, dict] | None = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    def sheet(wb, title, header, data, widths):
        ws = wb.create_sheet(title)
        ws.append(header)
        for r in data:
            ws.append(r)
        for c in ws[1]:
            c.font = Font(name="Arial", bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3864")
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial", size=10); c.alignment = Alignment(wrap_text=True, vertical="top")
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    metadata = metadata or {}
    wb = Workbook(); wb.remove(wb.active)
    legend = [
        ("Co to jest", "Lista DOSŁOWNYCH cytatów z dokumentów (zdania/akapity skopiowane z PDF-a, z numerem strony PDF). Program niczego nie parafrazuje ani nie generuje."),
        ("Jak czytać", "Kolumna „kategoria” i „temat” to oznaczenie słownikowe (reguły w lexicon.py), a „słowa kluczowe” pokazują, co o nim zdecydowało. "
                       "Zdanie może mieć kilka tematów (wtedy cytat się powtarza; ten sam id_cytatu) albo żadnego. Oznaczenia są pomocą w czytaniu, nie ostatecznym kodowaniem."),
        ("Typ", "zdanie = tekst ciągły; tabela/kwoty = wiersz tabeli (liczby w kolejnych latach, kwoty) — pozostawiony dla kategorii Finanse i Zasób."),
        ("Poziom działań", "A = działania własne (rozszerzanie oferty mieszkaniowej: budowa, zakup, TBS/SIM, mieszkania chronione/wspierane, wychodzenie z bezdomności, dopłaty); "
                           "B = zarządzanie i utrzymanie zasobu; C = obowiązki ustawowe i osłona najemców; G = deklaracja ogólna (zapowiedź działań mieszkaniowych bez nazwanego instrumentu, typowa dla strategii). To założenie badawcze (taxonomy.POLICY_TIER)."),
        ("Własna polityka", "Arkusz Własna_polityka: TAK / PRAWDOPODOBNIE / NIE / BRAK DANYCH na podstawie cytatów o działaniach poziomu A. Nie liczą się cytaty zaprzeczone (np. „nie będzie…”) ani bez sygnału działania (same opisy stanu, np. wzmianka w SWOT) — kolumna „sygnał działania”. "
                            "To ocena TREŚCI DOKUMENTÓW (deklaracje), nie faktycznej realizacji."),
        ("Ograniczenia", "Brak oznaczenia nie znaczy, że tematu nie ma w dokumencie. Tekst ze skanów (OCR) może mieć błędy — sprawdź w PDF-ie (kolumna n_stron_OCR w arkuszu Dokumenty)."),
    ]
    sheet(wb, "Legenda", ["Element", "Opis"], legend, [24, 130])
    docs = []
    for s in summaries:
        m = metadata.get(s["doc_id"], {})
        docs.append([s["doc_id"], s["miasto"], s["typ_dokumentu"], m.get("resolution_number"), m.get("adoption_date"), m.get("period_start"), m.get("period_end"),
                     "tak" if m.get("is_amendment") else "", s["n_stron"], s["n_stron_OCR"], s["cytaty_Problem"], s["cytaty_Zasób i stan"], s["cytaty_Finanse"],
                     s["cytaty_Cel/priorytet"], s["cytaty_Działanie"], s["poziom_A"], s["poziom_B"], s["poziom_C"], s["poziom_G"]])
    sheet(wb, "Dokumenty", ["doc_id", "miasto", "typ", "nr uchwały", "data uchwalenia", "okres od", "okres do", "nowelizacja", "n_stron", "n_stron_OCR",
                            "cytaty: problemy", "cytaty: zasób i stan", "cytaty: finanse", "cytaty: cele", "cytaty: działania", "działania A", "działania B", "działania C", "deklaracje ogólne G"],
          docs, [30, 16, 8, 16, 14, 9, 9, 11, 9, 11, 11, 11, 11, 10, 11, 10, 10, 10, 12])
    quotes = [[r["doc_id"], r["miasto"], r["typ_dokumentu"], r["strona"], r["kategoria"], r["temat"], r["cytat"], r["typ"], r.get("status", ""), r.get("kierunek", ""),
               r.get("poziom", ""), r.get("sygnal", ""), r["slowa_kluczowe"], r["id_cytatu"]] for r in rows]
    sheet(wb, "Cytaty", ["doc_id", "miasto", "typ dok.", "strona PDF", "kategoria", "temat", "CYTAT", "typ", "status działania", "kierunek", "poziom", "sygnał działania", "słowa kluczowe", "id_cytatu"],
          quotes, [28, 14, 8, 8, 14, 36, 110, 11, 16, 16, 7, 9, 30, 9])
    by_city = defaultdict(list)
    for s in summaries:
        by_city[s["miasto"] or s["doc_id"]].append(s)
    own_rows = []
    for city, ds in sorted(by_city.items()):
        v = city_verdict(ds)
        own_rows.append([city, ", ".join(d["typ_dokumentu"] for d in ds), v["werdykt"], v["A"]["n"], "; ".join(f"{k} (×{n})" for k, n in v["A"]["instruments"].most_common()),
                         "\n".join(v["A"]["examples"][:4]), v["B"]["n"], v["C"]["n"], v["G"]["n"], "\n".join(v["G"]["examples"][:3])])
    sheet(wb, "Własna_polityka", ["miasto", "dokumenty", "czy są działania własne (A)?", "cytaty A", "instrumenty A", "przykładowe cytaty A (do 4)", "cytaty B", "cytaty C", "deklaracje ogólne G", "przykłady G (do 3)"],
          own_rows, [18, 14, 46, 9, 44, 110, 9, 9, 12, 90])
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); wb.save(p)
    return p
