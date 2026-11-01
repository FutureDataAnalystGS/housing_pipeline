"""Tryb „kandydaci”: słownik wybiera zdania, które MOGĄ opisywać problem/działanie, a model lokalny tylko je klasyfikuje.

Dlaczego: otwarte „znajdź wszystkie problemy w fragmencie” jest dla małego modelu (7B) za trudne — miesza wiersze tabel,
definicje i opisy działań z problemami. Klasyfikacja pojedynczych zdań jest znacznie prostsza, krótsza (mniej tokenów do
wygenerowania, więc szybciej na CPU), a cytat jest z definicji dokładny (to zdanie z dokumentu), bez zmyślonych cytatów i stron.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ingest import Page, normalize_for_search
from .lexicon import baseline_instruments, baseline_problems


@dataclass
class Unit:
    page: int
    text: str


_LIST_START = re.compile(r"^(?:\d{1,2}[.)]|[a-ząćęłńóśźż][.)]|[-•–])\s")
_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9„\"(])")


def build_units(pages: list[Page], max_chars: int = 380) -> list[Unit]:
    """Akapity/zdania ze stron. Elementy list łączymy z poprzednim wierszem („…w tym:” + „1) 103 budynki…”), by zachować kontekst."""
    units: list[Unit] = []
    for pg in pages:
        buf = ""
        for blk in re.split(r"\n\s*\n", pg.text):
            t = normalize_for_search(blk)
            if not t:
                continue
            joins = buf and (_LIST_START.match(t) or t[0].islower() or buf.endswith((":", ","))) and len(buf) + len(t) < max_chars + 120
            if joins:
                buf = f"{buf} {t}"
            else:
                if buf:
                    units.append(Unit(pg.page, buf))
                buf = t
        if buf:
            units.append(Unit(pg.page, buf))
    out: list[Unit] = []
    for u in units:                                    # długie akapity dzielimy na zdania i składamy do ≤ max_chars
        if len(u.text) <= max_chars:
            out.append(u)
            continue
        cur = ""
        for s in _SENT_SPLIT.split(u.text):
            if cur and len(cur) + len(s) + 1 > max_chars:
                out.append(Unit(u.page, cur))
                cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            out.append(Unit(u.page, cur))
    return [u for u in out if len(u.text) >= 25]


_P_CUES = re.compile(
    r"brak|niedobór|niedostat|niewystarcz|zły|zła|złe|zaległ|zadłuż|zagroż|konieczn|obowiązek|obowiązk|problem|deficyt|nieopłacaln|zużyt|"
    r"eksmisj|bezdomn|kolejk|oczekując|zapotrzebowan|wymaga|niepodłączon|niesamodziel|piec|sutere|wyburz|katastrof|wyrok|"
    r"przed\s+19\d\d|najstarsz|wiek\w*\s+budynk|obniżon\w+\s+standard|ubytek|pustostan|nadmetraż|przeludnien|niezaspokojon|roszczen|odszkodowan", re.I)
_A_CUES = re.compile(
    r"planuje|zakłada|przewiduje|będzie|będą|zostan|realizuj|prowadz|kontynu|podejmie|podejmowa|dąży|wdroż|utworz|zakup|nabyw|\bbudow|remont|"
    r"modernizac|likwidac|sprzeda|termomodernizac|przekształc|dofinansow|przekaz|zapewni|zwiększ|powiększ|wstrzyma|ogranicz|scal|zamian|"
    r"windykac|odpracowan|obniżk|dodatk\w+\s+mieszkaniow|weryfikacj|partycypac|rewitalizac|adaptac|przystosow", re.I)
_NOT_TEXT = re.compile(r"\bart\.\s*\d+|Stosownie do|Dz\.\s*U\.|^[^.]{3,80}\s[—–]\s|\s-\s(?:budynek|lokal)\s", re.I)   # podstawa prawna, definicje


def _digit_share(t: str) -> float:
    c = t.replace(" ", "")
    return sum(ch.isdigit() for ch in c) / max(len(c), 1)


_TRAILING_NUMBERS = re.compile(r"(?:[-\d][\d.,%]*\s+){2,}[-\d][\d.,%]*\s*$")        # ≥3 liczby na końcu = wiersz tabeli


def is_table_like(t: str) -> bool:
    """Wiersz tabeli/kwoty: dużo cyfr albo ≥3 kolejne liczby na końcu („… 2 500 000”, „… 35 26 36 37 40”).
    Zdanie kończące się jedną liczbą/rokiem („do 2026”) ani lista z latami („1945 -1980,”) nie są wierszami tabeli."""
    return _digit_share(t) > 0.35 or bool(_TRAILING_NUMBERS.search(t))


def select(units: list[Unit], kind: str, require_housing: bool = False) -> list[Unit]:
    """require_housing=True (strategie): dodatkowo wymagamy mocnego terminu mieszkaniowego (lexicon.score ≥ 1)."""
    from .lexicon import score as housing_score
    out = []
    for u in units:
        t = u.text
        if _NOT_TEXT.search(t):
            continue
        if require_housing and housing_score(t) < 1.0:
            continue
        if kind == "problems":
            if is_table_like(t):                       # wskaźniki liczbowe zbierają bloki faktów, nie lista problemów
                continue
            if _P_CUES.search(t) or baseline_problems(t):
                out.append(u)
        elif kind == "actions":
            if _A_CUES.search(t) or baseline_instruments(t):
                out.append(u)
    return out


# ---- heurystyki zamiast pól, które mały model robi zawodnie (krótsza odpowiedź = szybciej i trafniej)
def severity(t: str) -> str:
    if re.search(r"głównym|główn\w+\s+problem|kluczow|podstawow\w+\s+(?:problem|wyzwani)|priorytet", t, re.I):
        return "key"
    return "notable" if re.search(r"\d", t) else "mention"


def act_status(t: str) -> str:
    if re.search(r"\bo\s+ile\b|\bjeżeli\b|\bjeśli\b|w\s+miarę\s+możliwości|w\s+przypadku\s+(?:gdy|konieczności)", t, re.I):
        return "conditional"
    if re.search(r"planuj|będzie|będą|zostan|zakłada\s+się|przewiduje\s+się|w\s+latach\s+20[2-3]\d", t, re.I):
        return "planned"
    return "existing"


def act_stance(t: str) -> str:
    if re.search(r"nie\s+będzie\s+prowadzon|wstrzyma|zaprzest|ogranicz|rezygnac", t, re.I):
        return "restrict"
    if re.search(r"zwiększ|powiększ|rozszerz|kolejn\w+\s+inwestycj|większej\s+liczby", t, re.I):
        return "expand"
    if re.search(r"kontynu|utrzym", t, re.I):
        return "maintain"
    return "not_applicable"


def budget_pln(t: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:,\d+)?\s*(?:zł|PLN)", t)
    return float(re.sub(r"\D", "", m.group(1))) if m else None
