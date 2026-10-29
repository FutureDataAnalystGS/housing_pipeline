"""Księga kodowa v0.1 jako modele Pydantic. Opisy pól (description) = definicje zmiennych w codebook.xlsx.
Każda wartość ma status (found / not_present / unclear) i dowód (strona + dosłowny cytat), co pozwala:
  * odróżnić „brak w dokumencie” od „nie znaleziono” (braki strukturalne vs. błąd ekstrakcji),
  * automatycznie zweryfikować, że cytat faktycznie występuje w dokumencie (audit trail).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from .taxonomy import GROUPS, INSTRUMENTS, PROBLEMS

ProblemCode = Enum("ProblemCode", {k: k for k in PROBLEMS}, type=str)
InstrumentCode = Enum("InstrumentCode", {k: k for k in INSTRUMENTS}, type=str)
GroupCode = Enum("GroupCode", {g: g for g in GROUPS}, type=str)


def _enum(name: str, *vals: str):
    return Enum(name, {v: v for v in vals}, type=str)


class Status(str, Enum):
    found = "found"                # wartość wprost w dokumencie
    not_present = "not_present"    # dokument nie zawiera tej informacji (brak strukturalny)
    unclear = "unclear"            # informacja jest, ale niejednoznaczna / niespójna


class Evidence(BaseModel):
    page: Optional[int] = Field(None, description="Numer strony z markera [[strona N]], na której jest cytat.")
    quote: str = Field(..., description="Dosłowny cytat z dokumentu (maks. 35 słów) potwierdzający wartość.")


class NumFact(BaseModel):
    value: Optional[float] = Field(None, description="Liczba dokładnie jak w dokumencie (kropka dziesiętna, bez spacji tysięcy).")
    unit: Optional[str] = Field(None, description="Jednostka: lokale, budynki, m2, zł, %, lata, osoby…")
    ref_date: Optional[str] = Field(None, description="Data/rok odniesienia wartości (np. 2020-12-31 lub 2021).")
    status: Status = Status.not_present
    evidence: list[Evidence] = Field(default_factory=list)


class BoolFact(BaseModel):
    value: Optional[bool] = None
    status: Status = Status.not_present
    evidence: list[Evidence] = Field(default_factory=list)


class TextFact(BaseModel):
    value: Optional[str] = Field(None, description="Krótki opis (maks. 30 słów), parafraza lub cytat.")
    status: Status = Status.not_present
    evidence: list[Evidence] = Field(default_factory=list)


def CatFact(enum_cls):
    return create_model(f"Cat_{enum_cls.__name__}", value=(Optional[enum_cls], None), status=(Status, Status.not_present),
                        evidence=(list[Evidence], Field(default_factory=list)))


def N(desc, rq="RQ3"):
    return Field(default_factory=NumFact, description=desc, json_schema_extra={"rq": rq, "kind": "liczba"})


def B(desc, rq="RQ2"):
    return Field(default_factory=BoolFact, description=desc, json_schema_extra={"rq": rq, "kind": "tak/nie"})


def T(desc, rq="RQ3"):
    return Field(default_factory=TextFact, description=desc, json_schema_extra={"rq": rq, "kind": "tekst"})


def C(enum_cls, desc, rq="RQ2"):
    cls = CatFact(enum_cls)
    return Field(default_factory=cls, description=desc + " Dozwolone: " + ", ".join(e.value for e in enum_cls),
                 json_schema_extra={"rq": rq, "kind": "kategoria"})


SalesPolicy = _enum("SalesPolicy", "halted", "selective", "continuing", "not_addressed")
RentTarget = _enum("RentTarget", "cost_recovery", "pct_replacement_value", "other", "not_addressed")
ManagerType = _enum("ManagerType", "city_office", "budget_unit", "municipal_company", "tbs", "mixed", "other")
ConditionRating = _enum("ConditionRating", "good", "satisfactory", "unsatisfactory", "bad", "not_assessed")
Trend = _enum("Trend", "increase", "stable", "decrease", "not_stated")
FundingSource = _enum("FundingSource", "rent", "municipal_budget", "subsidy_przedmiotowa", "bgk_fundusz_doplat",
                      "bgk_loans", "eu_funds", "sales_proceeds", "nfosigw", "kpo", "other")
Severity = _enum("Severity", "mention", "notable", "key")
GoalLevel = _enum("GoalLevel", "strategic_goal", "operational_goal", "direction", "priority", "project")
Dimension = _enum("Dimension", "spatial", "social", "market", "energy_climate", "stock_management")
Stance = _enum("Stance", "expand", "maintain", "restrict", "introduce", "not_applicable")
ActStatus = _enum("ActStatus", "existing", "planned", "conditional")
ProjType = _enum("ProjType", "komunalne", "socjalne", "tbs_sim", "chronione_wspierane", "other")
Integration = _enum("Integration", "none", "spatial_only", "single_direction", "dedicated_goal_or_priority", "dedicated_programme_or_section")


# =============================================================== BLOKI WPGMZ
class WStock(BaseModel):
    """W1. Wielkość i struktura zasobu (RQ3). Liczby tak, jak podaje dokument — NIE normalizuj definicji zasobu."""
    stock_ref_date: TextFact = T("Data, na którą podano stan zasobu (np. 31.12.2020).")
    units_total: NumFact = N("Łączna liczba lokali w mieszkaniowym zasobie gminy wg definicji dokumentu.")
    area_total_m2: NumFact = N("Łączna powierzchnia użytkowa lokali zasobu (m2).")
    buildings_total: NumFact = N("Łączna liczba budynków, w których są lokale zasobu.")
    units_gmina_100pct: NumFact = N("Lokale w budynkach stanowiących w 100% własność gminy.")
    units_wspolnoty: NumFact = N("Lokale gminy w budynkach wspólnot mieszkaniowych.")
    units_other_owners: NumFact = N("Lokale w budynkach innych właścicieli (spółdzielnie, Skarb Państwa, prywatne) administrowane lub wynajmowane przez gminę.")
    units_social_rent: NumFact = N("Lokale przeznaczone na najem socjalny.")
    units_temporary: NumFact = N("Pomieszczenia tymczasowe.")
    units_protected_supported: NumFact = N("Mieszkania chronione, wspierane i treningowe (zasób gminy + MOPS).")
    units_company_tbs: NumFact = N("Lokale w zasobie gminnej spółki/TBS/SIM wykazane odrębnie od zasobu gminy.")
    stock_definition_note: TextFact = T("Co dokument zalicza do zasobu (1–2 zdania) — potrzebne do oceny porównywalności.")


class WCondition(BaseModel):
    """W2. Stan techniczny i standard zasobu (RQ1, RQ3)."""
    buildings_pre1945_share_pct: NumFact = N("Udział budynków (lub lokali) sprzed 1945 r. w % — w polu unit wpisz 'budynki' albo 'lokale'.")
    condition_rating: Any = C(ConditionRating, "Ogólna ocena stanu technicznego zasobu wyrażona przez dokument.", "RQ1")
    share_buildings_need_major_repair_pct: NumFact = N("Udział budynków wymagających remontu kapitalnego/znacznych nakładów (%).")
    units_wc_outside: NumFact = N("Lokale z WC poza lokalem.")
    units_shared_facilities: NumFact = N("Lokale ze wspólnym użytkowaniem pomieszczeń (kuchnia/łazienka/WC).")
    units_coal_heating: NumFact = N("Lokale ogrzewane piecami na paliwa stałe.")
    units_basement: NumFact = N("Lokale w suterenach.")
    units_central_heating: NumFact = N("Lokale z centralnym ogrzewaniem.")


class WNeeds(BaseModel):
    """W3. Potrzeby mieszkaniowe (RQ1, RQ3)."""
    eviction_social_pending: NumFact = N("Wyroki eksmisyjne z prawem do lokalu socjalnego oczekujące na realizację (stan na dzień z dokumentu).", "RQ1")
    eviction_temporary_pending: NumFact = N("Wyroki bez prawa do lokalu socjalnego — zapotrzebowanie na pomieszczenia tymczasowe.", "RQ1")
    waiting_list_units: NumFact = N("Rodziny/gospodarstwa zakwalifikowane lub oczekujące na lokal komunalny (lista).", "RQ1")
    total_need_units: NumFact = N("Łączne zapotrzebowanie na lokale (komunalne + socjalne) podane w dokumencie.", "RQ1")
    arrears_share_pct: NumFact = N("Odsetek lokali/najemców zalegających z opłatami (%).", "RQ1")
    arrears_total_pln: NumFact = N("Łączna kwota zaległości (zł).", "RQ1")
    need_trend: Any = C(Trend, "Prognozowany kierunek zapotrzebowania na lokale socjalne/komunalne w okresie programu.", "RQ1")
    priority_groups: list[GroupCode] = Field(default_factory=list, description="Grupy wskazane jako priorytetowe adresaci polityki (kody grup).")


class Project(BaseModel):
    name: str = Field(..., description="Nazwa/adres inwestycji.")
    units: Optional[float] = Field(None, description="Liczba lokali.")
    type: Optional[ProjType] = None
    year: Optional[int] = Field(None, description="Rok planowanego zakończenia.")
    financing_source: Optional[str] = None
    evidence: Optional[Evidence] = None


class WForecast(BaseModel):
    """W4. Prognoza zasobu i inwestycje (RQ3, RQ5)."""
    forecast_start_year: NumFact = N("Pierwszy rok prognozy zasobu.", "RQ5")
    forecast_end_year: NumFact = N("Ostatni rok prognozy zasobu.", "RQ5")
    stock_start_units: NumFact = N("Liczba lokali na początku prognozy (tabela prognozy zasobu).", "RQ5")
    stock_end_units: NumFact = N("Liczba lokali na końcu prognozy.", "RQ5")
    planned_new_units_total: NumFact = N("Suma lokali planowanych do wybudowania w okresie programu.", "RQ5")
    planned_purchases_units_total: NumFact = N("Suma lokali planowanych do zakupu/pozyskania.", "RQ5")
    planned_demolitions_units_total: NumFact = N("Suma lokali w budynkach planowanych do rozbiórki/wykwaterowania.", "RQ5")
    planned_sales_units_total: NumFact = N("Suma lokali planowanych do sprzedaży w okresie programu.", "RQ5")
    new_projects: list[Project] = Field(default_factory=list, description="Nazwane inwestycje mieszkaniowe zapowiedziane w dokumencie.")


class WSales(BaseModel):
    """W6. Polityka sprzedaży (RQ2, RQ5)."""
    sales_policy: Any = C(SalesPolicy, "Stanowisko wobec sprzedaży lokali: halted = wstrzymana, selective = wybrane kategorie, continuing = rutynowa sprzedaż.", "RQ5")
    sales_units_per_year: NumFact = N("Planowana roczna liczba sprzedawanych lokali.", "RQ5")
    sales_revenue_total_pln: NumFact = N("Planowane wpływy ze sprzedaży w okresie programu (zł).", "RQ5")
    sales_proceeds_use: TextFact = T("Na co mają być przeznaczone wpływy ze sprzedaży.", "RQ5")


class WRepairs(BaseModel):
    """W5. Remonty i modernizacje (RQ2, RQ5)."""
    outlays_repairs_total_pln: NumFact = N("Suma planowanych nakładów na remonty w okresie programu (zł, brutto jeśli podano).", "RQ5")
    outlays_modernization_total_pln: NumFact = N("Suma planowanych nakładów na modernizacje/inwestycje w okresie programu (zł).", "RQ5")
    repair_priority_safety_first: BoolFact = B("Czy dokument deklaruje priorytet bezpieczeństwa (remonty awaryjne) przed standardem.", "RQ5")
    thermo_program: BoolFact = B("Czy planowana jest termomodernizacja zasobu.")
    thermo_buildings_n: NumFact = N("Liczba budynków objętych termomodernizacją.", "RQ5")
    stoves_elimination_units_n: NumFact = N("Liczba lokali/pieców do likwidacji (niska emisja).", "RQ5")
    tenant_funded_renovation: BoolFact = B("Czy dopuszczono remont na koszt najemcy (w zamian za najem).")


class WRent(BaseModel):
    """W7. Polityka czynszowa (RQ2, RQ5)."""
    rent_target: Any = C(RentTarget, "Cel polityki czynszowej.", "RQ5")
    rent_target_pct_replacement_value: NumFact = N("Docelowy czynsz jako % wartości odtworzeniowej lokalu w skali roku.", "RQ5")
    rent_zones_n: NumFact = N("Liczba stref lokalizacyjnych w systemie czynszowym.", "RQ5")
    rent_reduction_low_income: BoolFact = B("Czy przewidziano dochodowe obniżki czynszu.")
    income_verification: BoolFact = B("Czy przewidziano okresową weryfikację dochodów najemców.")
    income_verification_interval_years: NumFact = N("Częstotliwość weryfikacji dochodów (lata).", "RQ5")
    social_rent_max_pct_of_lowest: NumFact = N("Maks. stawka czynszu socjalnego jako % najniższego czynszu w zasobie.", "RQ5")
    debt_workoff_allowed: BoolFact = B("Czy dopuszczono odpracowanie zadłużenia.")


class WMgmt(BaseModel):
    """W8. Zarządzanie zasobem (RQ3)."""
    manager_type: Any = C(ManagerType, "Forma organizacyjna zarządcy zasobu.", "RQ3")
    manager_name: TextFact = T("Nazwa zarządcy (ZLiBK, ZGL, ZBM…).")
    participatory_mgmt: BoolFact = B("Czy deklarowane jest zarządzanie partycypacyjne/aktywizacja najemców.")
    mgmt_change_planned: BoolFact = B("Czy zapowiedziano zmianę modelu zarządzania.")
    exchange_programme: BoolFact = B("Czy działa/planowany jest system zamian lokali.")
    debt_collection_described: BoolFact = B("Czy opisano procedury windykacji.")


class WFinance(BaseModel):
    """W9. Finansowanie i koszty (RQ3, RQ5)."""
    costs_year: NumFact = N("Rok, dla którego podano poniższe wartości roczne (pierwszy rok programu).", "RQ5")
    rent_revenue_y1_pln: NumFact = N("Wpływy czynszowe z lokali mieszkalnych w pierwszym roku programu (zł).", "RQ5")
    budget_subsidy_y1_pln: NumFact = N("Środki z budżetu gminy/dotacja przedmiotowa na zasób w pierwszym roku (zł).", "RQ5")
    total_costs_y1_pln: NumFact = N("Łączne koszty gospodarki mieszkaniowej w pierwszym roku (eksploatacja + remonty + modernizacje) (zł).", "RQ5")
    financing_sources: list[FundingSource] = Field(default_factory=list, description="Źródła finansowania wymienione w dokumencie.")
    external_funding_planned: BoolFact = B("Czy planowane jest pozyskiwanie środków zewnętrznych (BGK, UE, KPO).", "RQ5")


# =============================================================== POZYCJE (długie tabele): problemy, cele, działania
class ProblemItem(BaseModel):
    category: ProblemCode = Field(..., description="Kod problemu P01–P99 wg księgi kodowej.")
    statement: str = Field(..., description="Parafraza problemu (maks. 30 słów).")
    severity: Severity = Field(..., description="mention = wzmianka; notable = wyraźnie opisany; key = nazwany wyzwaniem kluczowym/priorytetowym.")
    quantified: bool = Field(False, description="Czy problem poparto liczbą/wskaźnikiem.")
    quant_text: Optional[str] = Field(None, description="Liczba/wskaźnik jak w dokumencie.")
    affected_groups: list[GroupCode] = Field(default_factory=list)
    section: Optional[str] = Field(None, description="Nazwa sekcji/rozdziału dokumentu.")
    evidence: Evidence


class GoalItem(BaseModel):
    level: GoalLevel
    statement: str = Field(..., description="Parafraza celu/kierunku dot. mieszkalnictwa (maks. 30 słów).")
    dimension: Dimension = Field(..., description="Ujęcie: spatial (urbanistyka), social (dostępność/wykluczenie), market (rynek), energy_climate, stock_management.")
    evidence: Evidence


class ActionItem(BaseModel):
    instrument: InstrumentCode = Field(..., description="Kod instrumentu I01–I99.")
    description: str = Field(..., description="Co dokładnie planuje/prowadzi gmina (maks. 30 słów).")
    stance: Stance = Field(Stance.not_applicable, description="expand/maintain/restrict/introduce; dla sprzedaży 'restrict' = wstrzymanie lub ograniczenie.")
    status: ActStatus = Field(..., description="existing = istniejące i kontynuowane; planned = nowe, zaplanowane; conditional = zależne od środków/warunków.")
    named_instrument: bool = Field(True, description="False, jeśli to tylko ogólna deklaracja bez nazwanego narzędzia.")
    has_target_value: bool = Field(False, description="Czy podano wartość docelową/skalę (liczba lokali, budynków, osób).")
    target_text: Optional[str] = None
    has_budget_or_source: bool = Field(False, description="Czy podano budżet lub źródło finansowania.")
    budget_pln: Optional[float] = None
    has_deadline_or_owner: bool = Field(False, description="Czy podano termin lub podmiot odpowiedzialny.")
    responsible: Optional[str] = None
    period: Optional[str] = None
    addresses_problems: list[ProblemCode] = Field(default_factory=list, description="Problemy, na które działanie odpowiada WPROST w tekście.")
    link_explicit: bool = Field(False, description="True, jeśli dokument sam wiąże działanie z problemem.")
    evidence: Evidence


class HousingItems(BaseModel):
    """Pozycje do analizy RQ1, RQ2, RQ4 (kodowane z całego dokumentu WPGMZ lub z wybranych pasaży strategii)."""
    relevant: bool = Field(..., description="False, jeśli w podanym tekście nie ma treści o polityce mieszkaniowej.")
    problems: list[ProblemItem] = Field(default_factory=list)
    goals: list[GoalItem] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)


class StrategyFrame(BaseModel):
    """S. Ujęcie mieszkalnictwa w strategii (RQ1, RQ2, RQ5)."""
    integration_level: Any = C(Integration, "Miejsce mieszkalnictwa w strategii: none; spatial_only (tylko funkcja przestrzenna); single_direction; dedicated_goal_or_priority; dedicated_programme_or_section.", "RQ5")
    framing: list[Dimension] = Field(default_factory=list, description="Sposoby ujęcia mieszkalnictwa występujące w dokumencie.")
    references_wpgmz: BoolFact = B("Czy strategia odsyła do programu gospodarowania zasobem mieszkaniowym / polityki mieszkaniowej jako dokumentu dziedzinowego.", "RQ4")
    references_sim_tbs: BoolFact = B("Czy wspomina TBS/SIM/mieszkania czynszowe.", "RQ2")
    housing_indicators_n: NumFact = N("Liczba wskaźników monitorowania dotyczących mieszkalnictwa.", "RQ5")
    housing_directions_n: NumFact = N("Liczba kierunków/działań/projektów dotyczących mieszkalnictwa polityki (nie przestrzeni).", "RQ5")
    total_directions_n: NumFact = N("Łączna liczba kierunków/działań/projektów w strategii (jeśli policzalna).", "RQ5")
    diagnosis_housing_data: TextFact = T("Dane ilościowe o mieszkalnictwie w diagnozie (np. m2 na mieszkanie, nowe mieszkania) — lista w jednym polu.", "RQ1")


WPGMZ_BLOCKS: list[tuple[str, type[BaseModel], list[str]]] = [
    # (nazwa bloku, model, elementy ustawowe, z których składamy tekst)
    ("stock_condition_needs", create_model("WBlock1", stock=(WStock, ...), condition=(WCondition, ...), needs=(WNeeds, ...)), ["E1"]),
    ("forecast_sales", create_model("WBlock2", forecast=(WForecast, ...), sales=(WSales, ...)), ["E1", "E3", "E8"]),
    ("repairs", create_model("WBlock3", repairs=(WRepairs, ...)), ["E2"]),
    ("rent_mgmt", create_model("WBlock4", rent=(WRent, ...), mgmt=(WMgmt, ...)), ["E4", "E5"]),
    ("finance", create_model("WBlock5", finance=(WFinance, ...)), ["E6", "E7"]),
]
STRATEGY_FRAME_BLOCK = ("strategy_frame", StrategyFrame, [])


# =============================================================== schemat JSON dla LLM (bez $ref, pola WYMAGANE)
_META_KEYS = {"title", "rq", "kind", "default"}          # metadane księgi kodowej — nie trafiają do schematu modelu
P_LABELS = [f"{k} {v['name']}" for k, v in PROBLEMS.items()]
I_LABELS = [f"{k} {v['name']}" for k, v in INSTRUMENTS.items()]


def _resolve(node, defs):
    if isinstance(node, list):
        return [_resolve(v, defs) for v in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = _resolve(defs[node["$ref"].split("/")[-1]], defs)
        extra = {k: _resolve(v, defs) for k, v in node.items() if k != "$ref" and k not in _META_KEYS}
        return {**target, **extra}
    if "allOf" in node and len(node["allOf"]) == 1:
        rest = {k: v for k, v in node.items() if k != "allOf"}
        return _resolve({**node["allOf"][0], **rest}, defs)
    out = {}
    for k, v in node.items():
        if k == "properties":                              # klucze = nazwy pól (np. pole o nazwie "type")
            out[k] = {pk: _resolve(pv, defs) for pk, pv in v.items()}
        elif k in _META_KEYS:
            continue
        else:
            out[k] = _resolve(v, defs)
    return out


def _strictify(node):
    """Każde pole obiektu jest wymagane (inaczej mały model „oszczędza” i zwraca prawie pusty JSON)."""
    if isinstance(node, dict):
        if "properties" in node:
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False
        for v in node.values():
            _strictify(v)
    elif isinstance(node, list):
        for v in node:
            _strictify(v)
    return node


def _relabel(node):
    """Kody P01/I01 -> etykiety „P05 Niedobór zasobu…”: model widzi znaczenie kodu w samej gramatyce wyjścia."""
    if isinstance(node, dict):
        if "enum" in node and set(node["enum"]) == set(PROBLEMS):
            node["enum"] = P_LABELS
        elif "enum" in node and set(node["enum"]) == set(INSTRUMENTS):
            node["enum"] = I_LABELS
        for v in node.values():
            _relabel(v)
    elif isinstance(node, list):
        for v in node:
            _relabel(v)
    return node


def inline_schema(model: type[BaseModel], strict: bool = True, relabel: bool = True) -> dict:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    out = _resolve(schema, defs)
    if relabel:
        _relabel(out)
    return _strictify(out) if strict else out


_CODE = __import__("re").compile(r"^([PI]\d{2})(?:\s|$)")


def decode_labels(obj):
    """Odwrotność _relabel: „P05 Niedobór…” -> „P05” (rekurencyjnie, w polach category/instrument/addresses_problems)."""
    if isinstance(obj, dict):
        return {k: (_decode_one(v) if k in ("category", "instrument") else
                    [_decode_one(x) for x in v] if k == "addresses_problems" and isinstance(v, list) else decode_labels(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [decode_labels(v) for v in obj]
    return obj


def _decode_one(v):
    if isinstance(v, str):
        m = _CODE.match(v.strip())
        return m.group(1) if m else v
    return v


# =============================================================== „Odchudzone” modele dla małych modeli lokalnych
# Mniej pól = mniej błędów. Kolejność pól = kolejność „myślenia”: najpierw cytat, potem klasyfikacja.
class LlmProblem(BaseModel):
    quote: str = Field(..., description="Dosłowny cytat z tekstu (do 30 słów), z którego wynika problem.")
    page: int = Field(..., description="Numer strony z markera [[strona N]].")
    category: ProblemCode = Field(..., description="Kategoria problemu.")
    severity: Severity = Field(..., description="mention / notable / key")
    statement: str = Field(..., description="Problem własnymi słowami, maks. 25 słów.")


class LlmGoal(BaseModel):
    quote: str = Field(..., description="Dosłowny cytat z tekstu (do 30 słów).")
    page: int
    level: GoalLevel
    dimension: Dimension
    statement: str = Field(..., description="Cel własnymi słowami, maks. 25 słów.")


class LlmAction(BaseModel):
    quote: str = Field(..., description="Dosłowny cytat z tekstu (do 30 słów), z którego wynika działanie.")
    page: int
    instrument: InstrumentCode
    status: ActStatus
    stance: Stance
    description: str = Field(..., description="Działanie własnymi słowami, maks. 25 słów.")
    target_text: Optional[str] = Field(..., description="Wartość docelowa/skala (np. „23 budynki”) albo null.")
    budget_pln: Optional[float] = Field(..., description="Kwota w zł albo null.")
    period: Optional[str] = Field(..., description="Termin/okres (np. „2022-2026”) albo null.")
    responsible: Optional[str] = Field(..., description="Podmiot odpowiedzialny albo null.")


class LlmProblems(BaseModel):
    problems: list[LlmProblem]


class LlmGoals(BaseModel):
    goals: list[LlmGoal]


class LlmActions(BaseModel):
    actions: list[LlmAction]


def to_problem_item(p: dict) -> dict:
    q = p["quote"]
    return dict(category=p["category"], statement=p["statement"], severity=p["severity"],
                quantified=bool(__import__("re").search(r"\d", q)), quant_text=None, affected_groups=[], section=None,
                evidence=dict(page=p["page"], quote=q))


def to_goal_item(g: dict) -> dict:
    return dict(level=g["level"], statement=g["statement"], dimension=g["dimension"], evidence=dict(page=g["page"], quote=g["quote"]))


def to_action_item(a: dict) -> dict:
    return dict(instrument=a["instrument"], description=a["description"], stance=a["stance"], status=a["status"], named_instrument=True,
                has_target_value=bool(a.get("target_text")), target_text=a.get("target_text"),
                has_budget_or_source=a.get("budget_pln") is not None, budget_pln=a.get("budget_pln"),
                has_deadline_or_owner=bool(a.get("period") or a.get("responsible")), responsible=a.get("responsible"), period=a.get("period"),
                addresses_problems=[], link_explicit=False, evidence=dict(page=a["page"], quote=a["quote"]))
