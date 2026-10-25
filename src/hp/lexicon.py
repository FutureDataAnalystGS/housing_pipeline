"""Słownik do (a) wyszukiwania fragmentów o mieszkalnictwie w strategiach, (b) bazowego, deterministycznego
kodowania słownikowego (benchmark dla LLM). Dwa poziomy: terminy POLITYCZNE (mocne) i PRZESTRZENNE (słabe).

Uwaga merytoryczna: w strategiach dominuje „zabudowa mieszkaniowa” (funkcja przestrzenna, studium). To NIE jest
polityka mieszkaniowa. Dlatego terminy przestrzenne mają niską wagę i same nie wystarczają do uznania fragmentu.
"""
from __future__ import annotations

import re

STRONG = [
    r"mieszkalnictw\w*", r"zasob\w*\s+mieszkaniow\w*", r"zasób\w*\s+mieszkaniow\w*", r"potrzeb\w*\s+mieszkaniow\w*",
    r"polityk\w*\s+mieszkaniow\w*", r"gospodark\w*\s+mieszkaniow\w*", r"program\w*\s+gospodarowania\s+(?:mieszkaniowym\s+)?zasobem",
    r"lokal\w*\s+(?:komunaln|socjaln|zamienn|tymczasow|mieszkaln)\w*", r"najm\w*\s+(?:socjaln|komunaln)\w*",
    r"mieszka\w*\s+(?:komunaln|socjaln|chronion|wspierany|wspieran|treningow|czynszow|na\s+wynajem|dostępn)\w*",
    r"bezdomn\w*", r"wykluczeni\w*\s+mieszkaniow\w*", r"\bTBS\b", r"\bSIM\b", r"Społeczn\w+\s+Inicjatyw\w+\s+Mieszkaniow\w*",
    r"czynsz\w*", r"eksmisj\w*", r"dodat\w*\s+mieszkaniow\w*", r"budownictw\w*\s+(?:komunaln|socjaln|społeczn|czynszow|wielorodzinn\w*\s+na\s+wynajem)\w*",
    r"Mieszkani\w*\s+(?:Plus|na\s+start)", r"deficyt\w*\s+mieszka\w*", r"dostępność\s+mieszka\w*",
    r"zaspokaj\w*\s+potrzeb\w*\s+mieszkaniow\w*", r"remont\w*\s+(?:lokali|budynków)\s+(?:komunaln|gminn)\w*", r"najem\s+krótkoterminow\w*",
    r"rynek\s+(?:mieszkaniow|najmu)\w*",
]
ENERGY = [r"niskoemisj\w*", r"niska\s+emisj\w*", r"termomodernizacj\w*", r"wymian\w*\s+(?:źródeł\s+ciepła|pieców)", r"ubóstw\w*\s+energetyczn\w*"]
WEAK = [r"zabudow\w*\s+mieszkaniow\w*", r"tereny?\s+mieszkaniow\w*", r"osiedl\w*\s+mieszkaniow\w*", r"funkcj\w*\s+mieszkaniow\w*",
        r"strefa\s+mieszkalnictwa"]

_S = re.compile("|".join(STRONG), re.I)
_E = re.compile("|".join(ENERGY), re.I)
_W = re.compile("|".join(WEAK), re.I)

W_STRONG, W_ENERGY, W_WEAK = 1.0, 0.5, 0.25


def score(text: str) -> float:
    """Wynik trafności akapitu: terminy mocne 1.0, energetyczne 0.5 (tylko razem z mocnymi), przestrzenne 0.25."""
    s = len(_S.findall(text))
    e = len(_E.findall(text))
    w = len(_W.findall(text))
    return s * W_STRONG + (e * W_ENERGY if s else 0) + w * W_WEAK


def matched_terms(text: str) -> dict[str, int]:
    from collections import Counter
    c: Counter[str] = Counter(m.group(0).lower() for m in _S.finditer(text))
    return dict(c.most_common(10))


# --- bazowe kodowanie słownikowe instrumentów (benchmark; pełne kodowanie robi LLM)
INSTRUMENT_PATTERNS: dict[str, str] = {
    "I01": r"budow\w+\s+(?:budynk\w+|lokal\w+|mieszka\w+)\s+(?:komunaln|socjaln)\w*|budownictw\w*\s+komunaln\w*",
    "I02": r"\bTBS\b|\bSIM\b|Społeczn\w+\s+Inicjatyw\w+\s+Mieszkaniow\w*",
    "I03": r"(?:zakup|nabywani\w+|pozyskiwani\w+)\s+(?:lokal|budynk)\w*|adaptacj\w+\s+(?:budynk|pomieszcze)\w*",
    "I04": r"wynajm\w+\s+(?:lokal|mieszka)\w*\s+(?:od|na\s+wolnym)\w*|podnajm\w*",
    "I07": r"termomodernizacj\w*|likwidacj\w+\s+pieców|niskoemisj\w*",
    "I12": r"najem\s+socjaln\w*|lokal\w*\s+socjaln\w*|pomieszcze\w+\s+tymczasow\w*|lokal\w*\s+kryzysow\w*",
    "I13": r"mieszka\w+\s+(?:chronion|wspierany|wspieran|treningow)\w*",
    "I14": r"Housing\s+First|wychodzeni\w+\s+z\s+bezdomności|usamodzielni\w+",
    "I16": r"dodat\w+\s+mieszkaniow\w*",
    "I17": r"obniżk\w+\s+czynszu",
    "I18": r"odpracowani\w+|rozłożeni\w+\s+na\s+raty|ugod\w+",
    "I19": r"Mieszkanie\s+na\s+start|dopłat\w+\s+do\s+czynszu",
    "I20": r"zamian\w+\s+lokali|Biur\w+\s+Zamian",
    "I21": r"sprzedaż\w*\s+lokali|bonifikat\w+",
    "I22": r"weryfikacj\w+\s+(?:dochod|spełnian)\w*|stawk\w+\s+czynszu",
    "I23": r"windykacj\w*|egzekucj\w*",
    "I28": r"\bBGK\b|Fundusz\w*\s+Dopłat|\bKPO\b|Krajow\w+\s+Plan\w*\s+Odbudowy",
}
_INSTR = {k: re.compile(v, re.I) for k, v in INSTRUMENT_PATTERNS.items()}


def baseline_instruments(text: str) -> dict[str, int]:
    return {k: len(rx.findall(text)) for k, rx in _INSTR.items() if rx.search(text)}
