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
    "I01": r"\bbudow\w+\s+(?:budynk\w+|lokal\w+|mieszka\w+)\s+(?:komunaln|socjaln)\w*|budownictw\w*\s+komunaln\w*",
    "I02": r"\bTBS\b|\bSIM\b|Społeczn\w+\s+Inicjatyw\w+\s+Mieszkaniow\w*",
    "I03": r"(?:zakup|nabywani\w+|pozyskiwani\w+)\s+(?:lokal|budynk)\w*|adaptacj\w+\s+(?:budynk|pomieszcze)\w*",
    "I04": r"wynajm\w+\s+(?:lokal|mieszka)\w*\s+(?:od|na\s+wolnym)\w*|podnajm\w*",
    "I07": r"termomodernizacj\w*|likwidacj\w+\s+pieców|niskoemisj\w*",
    "I12": r"najem\s+socjaln\w*|lokal\w*\s+socjaln\w*|pomieszcze\w+\s+tymczasow\w*|lokal\w*\s+kryzysow\w*",
    "I13": r"mieszka(?:nia|ń|niach|niami|nie|niu)\s+(?:chronion|wspierany|wspieran|treningow)\w*",
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


# --- bazowe kodowanie słownikowe PROBLEMÓW (siatka bezpieczeństwa: jeśli słownik widzi problem, a model nic nie zwrócił
#     dla danego fragmentu, fragment trafia do kolejki przeglądu jako „possible_miss”)
PROBLEM_PATTERNS: dict[str, str] = {
    "P01": r"deficyt\w*\s+mieszka|niedobór\s+mieszka|brak\w*\s+(?:dostępn\w+\s+)?mieszka|dostępność\s+(?:cenow\w+\s+)?mieszka|ceny\s+mieszka",
    "P02": r"zły\s+stan\s+techniczn|stan\s+techniczn\w+[^.]{0,60}(?:niezadowalając|niedostateczn|zły|zły)|zużyci\w+\s+(?:techniczn|budynk)|wiek\w*\s+budynk|przed\s+1945|katastrof\w+\s+budowlan|nieopłacaln\w+\s+remont",
    "P03": r"WC\s+(?:usytuowane\s+)?poza\s+lokalem|wspóln\w+\s+użytkowani\w+\s+pomieszcze|obniżon\w+\s+standard|niesamodzieln\w+\s+lokal|sutere\w+",
    "P04": r"niska\s+emisj|piec\w+\s+(?:węglow|na\s+paliwo\s+stałe|grzewcz)|ubóstw\w+\s+energetyczn|smog",
    "P05": r"wyrok\w*\s+(?:o\s+|orzekając\w+\s+)?eksmisj|oczekując\w+\s+na\s+(?:najem|lokal)|zobowiązani\w+\s+gminy|brak\w*\s+lokali\s+socjaln|pomieszcze\w+\s+tymczasow",
    "P06": r"bezdomn|wykluczeni\w+\s+mieszkaniow|opuszczając\w+\s+(?:pieczę|placówk)",
    "P07": r"zaległo\w+\s+(?:czynszow|najemc|w\s+opłat)|zadłużeni\w+\s+najemc|ściągalno|nie\s+pokrywa\w*\s+kosztów",
    "P11": r"pustostan\w+|długi\s+czas\s+remont\w+|niewykorzystan\w+\s+(?:lokal|zasób)",
    "P13": r"brak\w*\s+(?:danych|monitoringu|polityki\s+mieszkaniow)|ograniczon\w+\s+środk\w+\s+finansow",
}
_PROB = {k: re.compile(v, re.I) for k, v in PROBLEM_PATTERNS.items()}


def baseline_problems(text: str) -> set[str]:
    return {k for k, rx in _PROB.items() if rx.search(text)}


# --- PEŁNE wzorce (tryb czytnika „cytaty”): wszystkie instrumenty i problemy, wiele etykiet na zdanie
INSTRUMENT_PATTERNS_FULL: dict[str, str] = {
    "I01": r"\bbudow\w+\s+(?:budynk\w+|lokal\w+|mieszka\w+)[^.]{0,40}(?:komunaln|socjaln|gminn)|budownictw\w*\s+(?:komunaln|socjaln)|inwestycj\w+\s+mieszkaniow|lokali\s+planowanych\s+do\s+wybudowania|powstanie\s+\d+\s+mieszka",
    "I02": r"\bTBS\b|\bSIM\b|Społeczn\w+\s+Inicjatyw\w+\s+Mieszkaniow\w*|\bKZN\b|Towarzystw\w+\s+Budownictwa\s+Społeczn",
    "I03": r"(?:zakup|nabywani\w+|pozyskiwani\w+)\s+(?:lokal|budynk|mieszka)\w*|lokali\s+planowanych\s+do\s+zakupu|adaptacj\w+\s+(?:budynk|pomieszcze)\w*|przekwalifikowan\w+",
    "I04": r"wynajm\w+\s+(?:lokal|mieszka)\w*[^.]{0,30}(?:wolnym\s+rynku|od\s+(?:osób|podmiot))|na\s+wolnym\s+rynku|podnajm\w*",
    "I05": r"grunt\w*\s+(?:gminn|pod\s+(?:zabudow|mieszkalnictw))|\bPPP\b|współprac\w+\s+z\s+deweloper\w+|partnerstw\w+\s+(?:publiczno|z\s+deweloper)",
    "I06": r"remont\w+|modernizac\w+",
    "I07": r"termomodernizac\w*|likwidacj\w+\s+pieców|piec\w+\s+na\s+(?:opał|paliwo)|niskoemisj\w*|\bOZE\b|przyłączeni\w+\s+do\s+(?:miejskiej\s+)?sieci\s+ciepłown",
    "I08": r"rozbiórk\w+|wyburz\w+|wykwaterowan\w+|likwidacj\w+\s+(?:lokali|niektórych|substandard)|scalani\w+",
    "I09": r"rewitalizac\w+",
    "I10": r"niepełnosprawn\w+|bez\s+barier|bezbarier\w+|\bwind\w+\b",
    "I11": r"kryteri\w+\s+(?:dochod|przydział|wynajm)|list\w+\s+(?:osób|oczekując)|komisj\w+\s+(?:do\s+spraw\s+)?mieszka|zasad\w+\s+wynajmowan",
    "I12": r"najem\s+socjaln\w*|lokal\w*\s+socjaln\w*|pomieszcze\w+\s+tymczasow\w*|lokal\w*\s+(?:zamienn|kryzysow)\w*",
    "I13": r"mieszka(?:nia|ń|niach|niami|nie|niu)\s+(?:chronion|wspierany|wspieran|treningow)\w*",
    "I14": r"Housing\s+First|wychodzeni\w+\s+z\s+bezdomności|usamodzielni\w+|pieczy\s+zastępcz\w+",
    "I15": r"mieszka\w+\s+(?:dla\s+(?:senior|młod\w+\s+rodzin|nauczyciel|pracowni\w+|rodzin\s+wielodzietn)|służbow)\w*|program\w*\s+(?:dla\s+)?senior\w+|mieszkani\w+\s+służbow\w+",
    "I16": r"dodat\w+\s+mieszkaniow\w*|dodat\w+\s+energetyczn\w*",
    "I17": r"obniżk\w+\s+czynszu|obniżen\w+\s+czynszu|obniżać\s+czynsz",
    "I18": r"odpracowani\w+|rozłożeni\w+\s+na\s+raty|\bugod\w+|trening\w*\s+budżetow\w+",
    "I19": r"Mieszkanie\s+na\s+start|dopłat\w+\s+do\s+(?:czynszu|najmu)",
    "I20": r"zamian\w+\s+lokal\w*|Biur\w+\s+Zamian|zamian\w+\s+mieszka\w*",
    "I21": r"sprzedaż\w*\s+(?:gminnych\s+)?lokali|sprzedaż\w*\s+lokal|bonifikat\w+|wykup\w*\s+lokal",
    "I22": r"stawk\w+\s+czynszu|polityk\w+\s+czynszow\w+|weryfikacj\w+\s+(?:dochod|spełnian)\w*|wartoś\w+\s+odtworzeniow\w+",
    "I23": r"windykac\w+|egzekucj\w+|wypowiedzeni\w+\s+umow|wezwani\w+\s+do\s+zapłaty",
    "I24": r"partycypacyjn\w+|zarządzani\w+\s+(?:zasobem|partycypac)|przekształceni\w+\s+(?:ZLiBK|zakład|jednostk)|cyfryzac\w+|upodmiotowieni\w+",
    "I25": r"miejscow\w+\s+plan|studium\s+uwarunkowań|planowani\w+\s+przestrzenn\w+|uzbrojeni\w+\s+teren\w+",
    "I26": r"obserwatori\w+|monitoring\w*\s+(?:rynku|potrzeb)|badani\w+\s+potrzeb|najem\s+krótkoterminow\w+",
    "I28": r"\bBGK\b|Fundusz\w*\s+Dopłat|\bKPO\b|Krajow\w+\s+Plan\w*\s+Odbudowy|środk\w+\s+(?:zewnętrzn|unijn)|fundusz\w+\s+(?:UE|europejsk)|NFOŚiGW|dofinansowan\w+",
    "I29": r"organizacj\w+\s+pozarządow\w+|\bNGO\b|spółdzielni\w+|współpra\w+\s+z\s+wspólnot",
}
PROBLEM_PATTERNS_FULL: dict[str, str] = {
    **PROBLEM_PATTERNS,
    "P01": PROBLEM_PATTERNS["P01"] + r"|brak\w*\s+mieszka|niewystarczając\w+\s+(?:liczb|podaż)",
    "P08": r"osób\s+(?:z\s+niepełnosprawn|starszych)|niepełnosprawn\w+|rodzin\w*\s+wielodzietn|młod\w+\s+rodzin|niesamodzieln\w+\s+i\s+zależn",
    "P09": r"starzen\w+\s+(?:się\s+)?(?:społeczeństw|ludności)|depopulac\w+|odpływ\w*\s+(?:młod|ludności)|migrac\w+|suburbaniz\w+",
    "P10": r"chaos\w*\s+przestrzenn|rozpraszan\w+\s+zabudow|rozlewan\w+|degradac\w+|brak\w*\s+infrastruktur",
    "P12": r"najem\s+krótkoterminow\w+|rynek\s+najmu|czynsz\w*\s+rynkow|ceny\s+(?:mieszka|najmu)",
    "P14": r"segregac\w+|koncentrac\w+\s+(?:problem|ubóstw)|patolog\w+|bezpieczeństw\w+",
}
_PROB_FULL = {k: re.compile(v, re.I) for k, v in PROBLEM_PATTERNS_FULL.items()}
_INSTR_FULL = {k: re.compile(v, re.I) for k, v in INSTRUMENT_PATTERNS_FULL.items()}
