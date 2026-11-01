"""Prompty dla modeli lokalnych. Kluczowa zasada: Ollama używa `format` (schemat JSON) tylko jako GRAMATYKI wyjścia —
model NIE widzi opisów pól ani definicji kodów ze schematu. Dlatego definicje księgi kodowej wstawiamy do promptu jawnie."""
from __future__ import annotations

from pydantic import BaseModel

from .taxonomy import FAMILIES, GROUPS, INSTRUMENTS, PROBLEMS

BASE = """Jesteś asystentem badawczym kodującym polskie dokumenty samorządowe o polityce mieszkaniowej miast (programy gospodarowania mieszkaniowym zasobem gminy, strategie rozwoju).
Zasady:
1. Koduj wyłącznie to, co wprost jest w podanym fragmencie. Nie dopowiadaj, nie zgaduj.
2. Każda pozycja MUSI mieć pole quote: dosłowny cytat skopiowany ze fragmentu (do 30 słów), oraz page: numer strony z najbliższego wcześniejszego znacznika [[strona N]].
3. Jeśli fragment nie zawiera żadnej pozycji tego typu, zwróć pustą listę. Pusta lista jest poprawną i częstą odpowiedzią.
4. Jedna pozycja = jedno stwierdzenie. Nie powtarzaj tej samej myśli.
5. Opis ogólnych przepisów prawa (np. co ustawa nakazuje gminie) nie jest problemem ani działaniem gminy, chyba że tekst mówi, jak to obciąża gminę lub co gmina zamierza zrobić."""


def problems_taxonomy(with_exclude: bool = True) -> str:
    lines = []
    for k, v in PROBLEMS.items():
        lines.append(f"{k} {v['name']} — {v['definition']}" + (f" NIE: {v['exclude']}" if (with_exclude and v["exclude"]) else ""))
    return "\n".join(lines)


def instruments_taxonomy() -> str:
    lines = []
    for fam, fname in FAMILIES.items():
        lines.append(f"[{fam} {fname}]")
        for k, v in INSTRUMENTS.items():
            if v["family"] == fam:
                lines.append(f"{k} {v['name']} — {v['definition']}")
    return "\n".join(lines)


SYSTEM_PROBLEMS = BASE + """

ZADANIE: znajdź PROBLEMY mieszkaniowe (diagnoza: stan rzeczy, braki, zagrożenia, niezaspokojone potrzeby, zaległości, zły stan zasobu). To NIE są cele ani działania gminy.
Wybierz category z listy (pole category musi być jedną z podanych etykiet):
""" + problems_taxonomy() + """

severity: mention = jedna wzmianka; notable = opisany wyraźnie (kilka zdań lub liczby); key = tekst nazywa to głównym/kluczowym problemem lub wyzwaniem.
Problemem są też liczby opisujące niedobór lub zły stan (np. liczba oczekujących na lokal, liczba lokali z piecami węglowymi, odsetek zalegających najemców)."""

SYSTEM_ACTIONS = BASE + """

ZADANIE: znajdź DZIAŁANIA gminy w polityce mieszkaniowej (istniejące, planowane lub warunkowe): co gmina robi lub zamierza zrobić.
Wybierz instrument z listy (pole instrument musi być jedną z podanych etykiet):
""" + instruments_taxonomy() + """

status: existing = już prowadzone/kontynuowane; planned = nowe, zaplanowane; conditional = zależne od środków lub warunków.
stance: expand = zwiększanie/rozwijanie; maintain = utrzymanie; restrict = ograniczanie lub wstrzymanie (np. wstrzymanie sprzedaży lokali); introduce = wprowadzenie nowego rozwiązania; not_applicable.
target_text, budget_pln, period, responsible: wypełnij tylko, gdy są w cytowanym fragmencie; w przeciwnym razie null.
Nie koduj jako działania samych definicji, tabel stawek czynszu bez decyzji, opisu struktury własności ani cytatów z ustaw."""

SYSTEM_GOALS = BASE + """

ZADANIE: znajdź CELE i kierunki polityki mieszkaniowej gminy (deklaracje, dokąd gmina zmierza), np. listę „głównych celów programu”.
level: strategic_goal / operational_goal / direction / priority / project.
dimension: spatial = urbanistyka i zabudowa; social = dostępność mieszkań, wykluczenie, grupy wsparcia; market = rynek, ceny, najem; energy_climate = energia, klimat, niska emisja; stock_management = zarządzanie zasobem gminy, remonty, finanse zasobu."""

# Przykłady (few-shot): krótkie, z prawdziwych dokumentów; jeden przykład pusty — uczy, że pusta lista jest dozwolona.
_EX_TEXT_1 = ("[[strona 3]]\nKonieczność tworzenia i powiększania zasobu lokali gminnych jest przede wszystkim następstwem regulacji ustawowej. "
              "Oznacza to, że obecnie każda wykonywana w mieście eksmisja wiąże się z obowiązkiem zapewnienia lokalu przez gminę. "
              "Sprzedaż gminnych lokali mieszkalnych na rzecz najemców nie będzie prowadzona.")
_EX_TEXT_0 = ("[[strona 9]]\nStawka czynszu najmu za 1 m2 dla mieszkaniowego zasobu gminy ustala Prezydent Miasta w drodze zarządzenia. "
              "Mieszkaniowy zasób gminy dzieli się na trzy strefy zamieszkania.")

FEWSHOT = {
    "problems": [
        (_EX_TEXT_1, '{"problems":[{"quote":"obecnie każda wykonywana w mieście eksmisja wiąże się z obowiązkiem zapewnienia lokalu przez gminę","page":3,"category":"P05 Niedobór zasobu komunalnego i socjalnego","severity":"key","statement":"Każda eksmisja obciąża gminę obowiązkiem dostarczenia lokalu."}]}'),
        (_EX_TEXT_0, '{"problems":[]}'),
    ],
    "actions": [
        (_EX_TEXT_1, '{"actions":[{"quote":"Sprzedaż gminnych lokali mieszkalnych na rzecz najemców nie będzie prowadzona","page":3,"instrument":"I21 Sprzedaż lokali","status":"existing","stance":"restrict","description":"Gmina wstrzymuje sprzedaż lokali komunalnych najemcom.","target_text":null,"budget_pln":null,"period":null,"responsible":null}]}'),
        (_EX_TEXT_0, '{"actions":[]}'),
    ],
    "goals": [
        ("[[strona 2]]\nDo głównych celów programu należą: 1. zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących mieszkańców, 2. poprawa jakości zamieszkania w mieszkaniowym zasobie gminy.",
         '{"goals":[{"quote":"zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących mieszkańców","page":2,"level":"strategic_goal","dimension":"social","statement":"Zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących."},{"quote":"poprawa jakości zamieszkania w mieszkaniowym zasobie gminy","page":2,"level":"strategic_goal","dimension":"stock_management","statement":"Poprawa jakości zamieszkania w zasobie gminy."}]}'),
        (_EX_TEXT_0, '{"goals":[]}'),
    ],
}
SYSTEMS = {"problems": SYSTEM_PROBLEMS, "actions": SYSTEM_ACTIONS, "goals": SYSTEM_GOALS}

# Profil „strict” (config: llm.prompt_profile: strict): ostrzejsza definicja problemu + przykłady negatywne.
# Powód: model 7B traktuje wiersze tabel, kwoty z budżetu, definicje i podstawę prawną jako „problemy”.
STRICT_PROBLEMS_RULES = """

TO NIE JEST PROBLEM (wtedy zwróć pustą listę dla tego fragmentu):
- wiersze tabel, same liczby i kwoty, pozycje budżetu i planu remontów;
- definicje pojęć (np. „budynek wymagający remontu bieżącego — budynek wymagający…”);
- podstawa prawna i uzasadnienie uchwały (art., ustawa, Dz.U.);
- opis tego, co gmina robi lub zapewnia (to są działania, nie problemy).
Problem to stwierdzenie o braku, niedoborze, złym stanie, zaległościach, zagrożeniu albo obowiązku, który obciąża gminę."""
SYSTEM_PROBLEMS_STRICT = BASE + """

ZADANIE: znajdź PROBLEMY mieszkaniowe (diagnoza: stan rzeczy, braki, zagrożenia, niezaspokojone potrzeby, zaległości, zły stan zasobu). To NIE są cele ani działania gminy.
Wybierz category z listy (pole category musi być jedną z podanych etykiet):
""" + problems_taxonomy(with_exclude=False) + """

severity: mention = jedna wzmianka; notable = opisany wyraźnie (kilka zdań lub liczby); key = tekst nazywa to głównym/kluczowym problemem lub wyzwaniem.""" + STRICT_PROBLEMS_RULES
FEWSHOT_STRICT_EXTRA = {"problems": [
    ("[[strona 7]]\nGmina Miasta Gdyni posiada 3 451 lokali wyposażonych w instalację centralnego ogrzewania i 309 lokali wyposażonych w piece grzewcze na paliwo stałe.",
     '{"problems":[{"quote":"309 lokali wyposażonych w piece grzewcze na paliwo stałe","page":7,"category":"P04 Efektywność energetyczna, niska emisja, klimat","severity":"notable","statement":"Część lokali ogrzewana jest piecami na paliwo stałe."}]}'),
    ("[[strona 6]]\nremonty dachów wraz z obróbkami blacharskimi i remontem kominów 2 500 000\nizolacja przeciwwilgociowa 1 000 000\nremonty instalacji sanitarnych 1 500 000", '{"problems":[]}'),
    ("[[strona 11]]\nbudynek wymagający remontu bieżącego — budynek wymagający wykonania robót polegających na stałej konserwacji urządzeń i elementów budynku.", '{"problems":[]}'),
    ("[[strona 20]]\nStosownie do art. 21 ust. 1 ustawy z dnia 21 czerwca 2001 r. Rada Gminy uchwala wieloletnie programy gospodarowania mieszkaniowym zasobem gminnym.", '{"problems":[]}'),
]}


def items_messages(kind: str, chunk: str, header: str = "", profile: str = "v1") -> list[dict]:
    strict = profile == "strict" and kind == "problems"
    msgs = [{"role": "system", "content": SYSTEM_PROBLEMS_STRICT if strict else SYSTEMS[kind]}]
    shots = (FEWSHOT_STRICT_EXTRA["problems"] + FEWSHOT["problems"][:1]) if strict else FEWSHOT[kind]
    for text, answer in shots:
        msgs += [{"role": "user", "content": f"<fragment>\n{text}\n</fragment>"}, {"role": "assistant", "content": answer}]
    msgs.append({"role": "user", "content": f"{header}<fragment>\n{chunk}\n</fragment>"})
    return msgs


# ---------------------------------------------------------------- bloki faktów (liczby, zmienne polityki)
FACTS_SYSTEM = BASE + """

ZADANIE: wypełnij WSZYSTKIE pola podanej struktury JSON na podstawie fragmentu dokumentu.
Dla każdego pola z wartością (liczba / tak-nie / tekst / kategoria): value, status, evidence.
- status = found, gdy wartość wprost jest w tekście; not_present, gdy fragment nie zawiera tej informacji (wtedy value=null, evidence=[]); unclear, gdy tekst jest niejednoznaczny lub sprzeczny.
- liczby: zapisz samą liczbę bez spacji tysięcy i z kropką dziesiętną (5 254 -> 5254; 218 584,97 -> 218584.97); w unit podaj jednostkę z dokumentu (lokale, m2, zł, tys. zł, %); w ref_date datę lub rok, którego liczba dotyczy.
- nie sumuj i nie przeliczaj sam, chyba że opis pola mówi „suma w okresie programu” i wszystkie lata są w tabeli.
- evidence: lista z cytatem (quote, dosłownie ze fragmentu) i numerem strony (page) dla każdej wartości found.
- listy (np. priority_groups): wybierz tylko dozwolone wartości; jeśli brak — pusta lista."""


def _kind(ann) -> str:
    name = getattr(ann, "__name__", str(ann))
    if name == "NumFact":
        return "liczba"
    if name == "BoolFact":
        return "tak/nie"
    if name == "TextFact":
        return "tekst"
    if name.startswith("Cat_"):
        return "kategoria"
    return "lista" if "list" in str(ann) else "obiekt"


def field_guide(model: type[BaseModel]) -> str:
    """Lista „ścieżka [typ]: opis” dla wszystkich pól bloku — to jest to, czego model nie widzi w samej gramatyce."""
    lines: list[str] = []
    for sub, f in model.model_fields.items():
        sm = f.annotation
        if hasattr(sm, "model_fields"):
            for var, vf in sm.model_fields.items():
                lines.append(f"- {sub}.{var} [{_kind(vf.annotation)}]: {vf.description or ''}")
        else:
            lines.append(f"- {sub} [{_kind(sm)}]: {f.description or ''}")
    return "\n".join(lines)


def facts_messages(model: type[BaseModel], chunk: str, header: str = "") -> list[dict]:
    sys = FACTS_SYSTEM + "\n\nPOLA DO WYPEŁNIENIA:\n" + field_guide(model)
    return [{"role": "system", "content": sys}, {"role": "user", "content": f"{header}<fragment>\n{chunk}\n</fragment>"}]


# ---------------------------------------------------------------- tryb „kandydaci”: klasyfikacja numerowanych zdań
def _problem_list() -> str:
    return "\n".join(f"{k} {v['name']} ({v['definition'][:85].rstrip(' ,;')}…)" for k, v in PROBLEMS.items() if k != "P99")


def _instrument_list() -> str:
    return "\n".join(f"{k} {v['name']}" for k, v in INSTRUMENTS.items() if k != "I99")


CLS_SYSTEM = {
    "problems": """Dostajesz numerowane zdania z polskiego dokumentu o polityce mieszkaniowej gminy. Dla KAŻDEGO zdania zdecyduj, czy OPISUJE PROBLEM mieszkaniowy (diagnoza: brak, niedobór, zły stan, zaległości, zagrożenie, niezaspokojona potrzeba, obowiązek obciążający gminę). Jeśli tak, podaj kod kategorii z listy. Jeśli zdanie opisuje to, co gmina robi, zapewnia lub planuje, albo jest definicją, zasadą, podstawą prawną lub opisem procedury — podaj NONE.
Odpowiedz JSON: {"results":[{"id":1,"label":"P05"},{"id":2,"label":"NONE"}]} dla każdego zdania, w kolejności.
Kategorie:
""" + _problem_list(),
    "actions": """Dostajesz numerowane zdania z polskiego dokumentu o polityce mieszkaniowej gminy. Dla KAŻDEGO zdania zdecyduj, czy opisuje DZIAŁANIE gminy w polityce mieszkaniowej (co gmina robi, zapewnia, planuje; także decyzję o wstrzymaniu lub ograniczeniu). Jeśli tak, podaj kod instrumentu z listy. Jeśli zdanie opisuje problem, definicję, podstawę prawną, zasadę ogólną albo nic konkretnego — podaj NONE.
Odpowiedz JSON: {"results":[{"id":1,"label":"I21"},{"id":2,"label":"NONE"}]} dla każdego zdania, w kolejności.
Instrumenty:
""" + _instrument_list(),
}
CLS_FEWSHOT = {
    "problems": ("[1] Gmina posiada 309 lokali wyposażonych w piece grzewcze na paliwo stałe.\n[2] Sprzedaż gminnych lokali na rzecz najemców nie będzie prowadzona.\n"
                 "[3] Stawkę czynszu ustala Prezydent Miasta w drodze zarządzenia.\n[4] Obecnie każda wykonywana w mieście eksmisja wiąże się z obowiązkiem zapewnienia lokalu przez gminę.",
                 '{"results":[{"id":1,"label":"P04"},{"id":2,"label":"NONE"},{"id":3,"label":"NONE"},{"id":4,"label":"P05"}]}'),
    "actions": ("[1] Sprzedaż gminnych lokali mieszkalnych na rzecz najemców nie będzie prowadzona.\n[2] Obecnie każda eksmisja wiąże się z obowiązkiem zapewnienia lokalu przez gminę.\n"
                "[3] Termomodernizacją zostanie objętych 23 budynki mieszkalne.\n[4] Lokale położone w suterenach zostaną przekwalifikowane na lokale użytkowe.",
                '{"results":[{"id":1,"label":"I21"},{"id":2,"label":"NONE"},{"id":3,"label":"I07"},{"id":4,"label":"I08"}]}'),
}


def classify_messages(kind: str, batch: list) -> list[dict]:
    ex_user, ex_ans = CLS_FEWSHOT[kind]
    listing = "\n".join(f"[{i}] {u.text}" for i, u in enumerate(batch, 1))
    return [{"role": "system", "content": CLS_SYSTEM[kind]}, {"role": "user", "content": ex_user}, {"role": "assistant", "content": ex_ans},
            {"role": "user", "content": listing}]
