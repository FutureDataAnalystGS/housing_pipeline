"""Ręcznie zakodowane rekordy (fixture) dla Gdyni i Olsztyna — cytaty skopiowane z dokumentów.
Służą do testu całego łańcucha bez wywołań API oraz jako PRZYKŁAD poprawnego kodowania (wzorzec dla kodujących)."""
from hp.extract_llm import fold_alnum
from hp.ingest import load_pages


def page_of(pages, quote):
    q = fold_alnum(quote)
    for p in pages:
        if q in fold_alnum(p.text):
            return p.page
    raise AssertionError(f"cytat nie występuje w dokumencie: {quote[:60]}")


def mk(pages):
    def num(v, unit, quote, ref=None):
        return dict(value=v, unit=unit, ref_date=ref, status="found", evidence=[dict(page=page_of(pages, quote), quote=quote)])

    def boo(v, quote):
        return dict(value=v, status="found", evidence=[dict(page=page_of(pages, quote), quote=quote)])

    def cat(v, quote):
        return dict(value=v, status="found", evidence=[dict(page=page_of(pages, quote), quote=quote)])

    def ev(quote):
        return dict(page=page_of(pages, quote), quote=quote)
    return num, boo, cat, ev


def gdynia(pages_dir="data/interim"):
    pages = load_pages("WPGMZ_Gdynia_2022-2026", pages_dir)
    num, boo, cat, ev = mk(pages)
    q_stock = "tworzy 5 254 lokali gminnych o łącznej powierzchni użytkowej 218 584,97"
    return dict(doc_id="WPGMZ_Gdynia_2022-2026", doc_type="WPGMZ",
        metadata=dict(resolution_number="XXXIV/1127/21", adoption_date="2021-10-27", period_start=2022, period_end=2026, is_amendment=False, needs_review=[]),
        blocks=dict(
            stock_condition_needs=dict(
                stock=dict(units_total=num(5254, "lokale", q_stock), area_total_m2=num(218584.97, "m2", q_stock),
                           units_wspolnoty=num(3590, "lokale", "3 590 lokali mieszkalnych w budynkach wspólnot mieszkaniowych"),
                           units_gmina_100pct=num(1503, "lokale", "1 503 lokali mieszkalnych w budynkach gminnych"),
                           units_other_owners=num(161, "lokale", "161 lokali mieszkalnych w 57 innych budynkach mieszkalnych"),
                           units_company_tbs=num(901, "lokale", "901 mieszkań w zasobach gminnej spółki"),
                           units_temporary=num(18, "pomieszczenia", "posiada 18 pomieszczeń tymczasowych")),
                condition=dict(units_coal_heating=num(309, "lokale", "309 lokali wyposażonych w piece grzewcze na paliwo stałe")),
                needs=dict(priority_groups=["low_income", "disabled", "seniors"])),
            forecast_sales=dict(
                forecast=dict(forecast_start_year=num(2022, "rok", "zasób mieszkaniowy 5 336 5 317 5 319 5 324 5 359"),
                              stock_start_units=num(5336, "lokale", "zasób mieszkaniowy 5 336 5 317 5 319 5 324 5 359", "2022"),
                              stock_end_units=num(5364, "lokale", "łącznie zasób mieszkaniowy 5 317 5 319 5 324 5 359 5 364", "2026"),
                              forecast_end_year=num(2026, "rok", "łącznie zasób mieszkaniowy 5 317 5 319 5 324 5 359 5 364"),
                              planned_new_units_total=num(51, "lokale", "liczba lokali planowanych do wybudowania 0 21 0 30 0"),
                              planned_purchases_units_total=num(25, "lokale", "liczba lokali planowanych do zakupu 5 5 5 5 5"),
                              planned_demolitions_units_total=num(48, "lokale", "liczba lokali w budynkach zaplanowanych do wyburzenia -24 -24 0 0 0"),
                              planned_sales_units_total=dict(value=0, unit="lokale", status="found", evidence=[ev("Sprzedaż gminnych lokali mieszkalnych na rzecz najemców nie będzie prowadzona")])),
                sales=dict(sales_policy=cat("halted", "Sprzedaż gminnych lokali mieszkalnych na rzecz najemców nie będzie prowadzona"))),
            repairs=dict(repairs=dict(thermo_program=boo(True, "będą objęte 23 budynki mieszkalne"), thermo_buildings_n=num(23, "budynki", "będą objęte 23 budynki mieszkalne"))),
            rent_mgmt=dict(rent=dict(rent_target_pct_replacement_value=num(3, "%", "Stawka czynszu najmu nie może przekroczyć 3% wartości odtworzeniowej lokalu"),
                                     income_verification=boo(True, "Okresowa weryfikacja spełniania przez najemców kryterium wartości dochodu")),
                           mgmt=dict(participatory_mgmt=boo(True, "dążyć będą do maksymalnie partycypacyjnego zarządzania"))),
            finance=dict(finance=dict(rent_revenue_y1_pln=num(23880000, "zł", "wpływy czynszowe z najmu lokali mieszkalnych 23 880 000", "2022")))),
        items=dict(relevant=True,
            problems=[dict(category="P05", statement="Każda eksmisja w mieście oznacza obowiązek zapewnienia lokalu przez gminę.", severity="key", quantified=True,
                           quant_text="598 wyroków (2021)", evidence=ev("obecnie każda wykonywana w mieście eksmisja wiąże się")),
                      dict(category="P02", statement="Budynki wyłącznie gminne należą do najstarszych w zasobie (103 z 150 sprzed 1945).", severity="notable", quantified=True,
                           quant_text="103 z 150 budynków sprzed 1945", evidence=ev("103 budynki wybudowane przed 1945 rokiem")),
                      dict(category="P04", statement="Część lokali ogrzewana piecami na paliwo stałe.", severity="notable", quantified=True, quant_text="309 lokali",
                           evidence=ev("309 lokali wyposażonych w piece grzewcze na paliwo stałe"))],
            goals=[dict(level="strategic_goal", statement="Zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących mieszkańców.", dimension="social",
                        evidence=ev("zaspokajanie potrzeb mieszkaniowych najbardziej potrzebujących mieszkańców"))],
            actions=[dict(instrument="I21", description="Wstrzymanie sprzedaży lokali najemcom.", stance="restrict", status="existing", named_instrument=True,
                          has_target_value=False, has_budget_or_source=False, has_deadline_or_owner=False, addresses_problems=["P05"], link_explicit=True,
                          evidence=ev("duże zapotrzebowanie na wynajem lokali komunalnych")),
                     dict(instrument="I07", description="Termomodernizacja 23 budynków i likwidacja pieców.", stance="expand", status="planned", named_instrument=True,
                          has_target_value=True, target_text="23 budynki", has_budget_or_source=True, budget_pln=5600000, has_deadline_or_owner=True, period="2022-2026",
                          addresses_problems=["P04"], link_explicit=False, evidence=ev("będą objęte 23 budynki mieszkalne")),
                     dict(instrument="I02", description="Budowa budynków przez TBS zasiedlanych przez osoby wskazane przez gminę.", stance="maintain", status="existing",
                          named_instrument=True, has_target_value=False, has_budget_or_source=False, has_deadline_or_owner=False, addresses_problems=[], link_explicit=False,
                          evidence=ev("budowę budynków z lokalami mieszkalnymi przez TBS"))]))


def olsztyn(pages_dir="data/interim"):
    pages = load_pages("WPGMZ_Olsztyn_2022-2026", pages_dir)
    num, boo, cat, ev = mk(pages)
    return dict(doc_id="WPGMZ_Olsztyn_2022-2026", doc_type="WPGMZ",
        metadata=dict(resolution_number="XXXIX/647/21", adoption_date="2021-11-24", period_start=2022, period_end=2026, is_amendment=False, needs_review=[]),
        blocks=dict(
            stock_condition_needs=dict(
                stock=dict(units_total=num(4035, "lokale", "pozostawało łącznie 4 035 lokali", "2020-12-31"),
                           area_total_m2=num(167876, "m2", "Razem 769 4 035 167 876", "2020-12-31"),
                           units_social_rent=num(335, "lokale", "stanowi 335 lokali przeznaczonych na najem socjalny", "2020-12-31"),
                           units_temporary=num(20, "pomieszczenia", "oraz 20 pomieszczeń tymczasowych", "2020-12-31")),
                condition=dict(units_coal_heating=num(561, "lokale", "Lokale ogrzewane piecami węglowymi 561", "2020-12-31")),
                needs=dict(arrears_share_pct=num(85.41, "%", "zaległości dotyczyły 3 543 lokali (85,41%", "2020"),
                           priority_groups=["low_income", "evicted", "care_leavers", "crisis_victims"])),
            forecast_sales=dict(
                forecast=dict(stock_start_units=num(3931, "lokale", "Łączna ilość lokali (szt.) 3931 3799 3755 3655 3555 3455", "2021-09-30"),
                              stock_end_units=num(3455, "lokale", "Łączna ilość lokali (szt.) 3931 3799 3755 3655 3555 3455", "2026"),
                              forecast_start_year=num(2022, "rok", "Łączna ilość lokali (szt.) 3931 3799 3755 3655 3555 3455"),
                              forecast_end_year=num(2026, "rok", "Łączna ilość lokali (szt.) 3931 3799 3755 3655 3555 3455"),
                              planned_new_units_total=num(56, "lokale", "powstanie 56 mieszkań o łącznej powierzchni 1 140,75")),
                sales=dict(sales_policy=cat("continuing", "Planuje się roczną sprzedaż lokali na poziomie zbliżonym do lat poprzednich"),
                           sales_units_per_year=num(100, "lokale/rok", "Rok Liczba sprzedanych lokali Dochód ze sprzedaży"))),
            repairs=dict(repairs=dict(tenant_funded_renovation=boo(True, "umowy na wykonanie remontu lokalu na koszt i staraniem przyszłego najemcy"))),
            rent_mgmt=dict(rent=dict(rent_target_pct_replacement_value=num(3, "%", "ukształtowania czynszów na poziomie 3 % wartości odtworzeniowej lokalu"),
                                     income_verification=boo(True, "nie częściej niż co 2,5 roku, weryfikuje spełnianie przez najemców"),
                                     income_verification_interval_years=num(2.5, "lata", "nie częściej niż co 2,5 roku, weryfikuje spełnianie przez najemców"),
                                     debt_workoff_allowed=boo(True, "Dyrektor ZLiBK może wyrazić zgodę na odpracowanie należności czynszowych")),
                           mgmt=dict(exchange_programme=boo(True, "działanie Biura Zamiany Mieszkań"))),
            finance=dict(finance=dict())),
        items=dict(relevant=True,
            problems=[dict(category="P07", statement="Główny problem: zaległości najemców; zaległości w 85% lokali.", severity="key", quantified=True, quant_text="85,41% lokali; 63 079 tys. zł",
                           evidence=ev("Głównym problemem w gospodarowaniu zasobem mieszkaniowym Gminy są zaległości najemców")),
                      dict(category="P03", statement="Lokale o obniżonym standardzie: WC poza lokalem, wspólne pomieszczenia, piece.", severity="notable", quantified=True,
                           quant_text="531 lokali z WC poza lokalem", evidence=ev("nadal znajdują się lokale o obniżonym standardzie"))],
            goals=[dict(level="operational_goal", statement="Poprawa dostępności lokali komunalnych dla gospodarstw o niskich dochodach.", dimension="social",
                        evidence=ev("poprawę dostępności lokali komunalnych dla gospodarstw domowych osiągających niskie dochody"))],
            actions=[dict(instrument="I01", description="Budowa 5 budynków (56 lokali socjalnych) przy ul. Towarowej, 2023.", stance="expand", status="planned", named_instrument=True,
                          has_target_value=True, target_text="56 lokali", has_budget_or_source=True, has_deadline_or_owner=True, period="2023", addresses_problems=["P05"], link_explicit=True,
                          evidence=ev("powstanie 56 mieszkań o łącznej powierzchni 1 140,75")),
                     dict(instrument="I21", description="Sprzedaż ok. 100 lokali rocznie w celu racjonalizacji zasobu.", stance="maintain", status="existing", named_instrument=True,
                          has_target_value=True, has_budget_or_source=True, has_deadline_or_owner=False, addresses_problems=[], link_explicit=False,
                          evidence=ev("Planuje się roczną sprzedaż lokali na poziomie zbliżonym do lat poprzednich")),
                     dict(instrument="I23", description="Dalsze działania windykacyjne wobec zadłużonych użytkowników.", stance="maintain", status="existing", named_instrument=True,
                          has_target_value=False, has_budget_or_source=False, has_deadline_or_owner=False, addresses_problems=["P07"], link_explicit=True,
                          evidence=ev("dalsze działania windykacyjne zgodnie z przyjętymi procedurami")),
                     dict(instrument="I20", description="Biuro Zamiany Mieszkań; prognozowane zamiany 7–11 rocznie.", stance="expand", status="existing", named_instrument=True,
                          has_target_value=True, has_budget_or_source=False, has_deadline_or_owner=True, addresses_problems=["P07"], link_explicit=True,
                          evidence=ev("kontynuację polityki zmierzającej do zamian lokali mieszkalnych"))]))
