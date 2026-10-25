"""Słowniki kodowe (księga kodowa v0.1): problemy, instrumenty, grupy, skale.

To jedyne źródło prawdy: z tego pliku generowane są schematy dla LLM,
arkusz codebook.xlsx oraz crosswalk problem -> instrument.
"""
from __future__ import annotations

# ------------------------------------------------------------------ PROBLEMY (diagnoza) -> RQ1, RQ4
PROBLEMS: dict[str, dict] = {
    "P01": dict(name="Niedobór mieszkań i dostępność cenowa",
                definition="Za mała podaż mieszkań lub zbyt wysokie ceny zakupu/czynsze względem dochodów; deficyt mieszkaniowy; trudności młodych i średnio zamożnych w uzyskaniu mieszkania.",
                exclude="Niedobór lokali komunalnych/socjalnych -> P05; rynek najmu -> P12."),
    "P02": dict(name="Stan techniczny i wiek zasobu",
                definition="Zły stan techniczny, zużycie, wiek budynków, kamienice/budynki wymagające remontu, zagrożenie katastrofą budowlaną, nieopłacalność remontów.",
                exclude="Braki wyposażenia lokali -> P03; efektywność energetyczna -> P04."),
    "P03": dict(name="Niski standard wyposażenia i metrażu lokali",
                definition="WC poza lokalem, brak łazienki, lokale wspólne, ogrzewanie piecami, sutereny, przeludnienie lub nadmetraż, lokale niesamodzielne.",
                exclude=""),
    "P04": dict(name="Efektywność energetyczna, niska emisja, klimat",
                definition="Niska efektywność energetyczna budynków, piece na paliwa stałe, smog, ubóstwo energetyczne, potrzeba adaptacji zasobu do zmian klimatu.",
                exclude=""),
    "P05": dict(name="Niedobór zasobu komunalnego i socjalnego",
                definition="Liczba lokali komunalnych/socjalnych/tymczasowych mniejsza niż potrzeby: kolejki, niezrealizowane wyroki eksmisyjne, zobowiązania gminy.",
                exclude="Bezdomność -> P06."),
    "P06": dict(name="Wykluczenie mieszkaniowe i bezdomność",
                definition="Bezdomność, zagrożenie utratą mieszkania, brak mieszkań chronionych/wspieranych/treningowych, trudności osób opuszczających pieczę zastępczą lub placówki.",
                exclude=""),
    "P07": dict(name="Zadłużenie najemców i finanse zasobu",
                definition="Zaległości czynszowe, niska ściągalność, czynsze nie pokrywają kosztów utrzymania, rosnące dopłaty z budżetu, koszty odszkodowań.",
                exclude=""),
    "P08": dict(name="Potrzeby grup szczególnych",
                definition="Brak mieszkań dostosowanych dla seniorów, osób z niepełnosprawnościami, młodych rodzin, rodzin wielodzietnych, kluczowych pracowników.",
                exclude="Bezdomni -> P06."),
    "P09": dict(name="Demografia i migracje a mieszkalnictwo",
                definition="Starzenie się, odpływ młodych, depopulacja, suburbanizacja, migracje (także z Ukrainy), zmiana struktury gospodarstw — w związku z mieszkalnictwem.",
                exclude="Sama demografia bez odniesienia do mieszkań nie jest kodowana."),
    "P10": dict(name="Problemy przestrzenne i urbanistyczne zabudowy mieszkaniowej",
                definition="Rozpraszanie zabudowy, chaos przestrzenny, braki infrastruktury w nowych osiedlach, degradacja obszarów mieszkaniowych, potrzeba rewitalizacji.",
                exclude="Wymóg: problem dotyczy funkcji mieszkaniowej, nie przestrzeni w ogóle."),
    "P11": dict(name="Pustostany i niewykorzystany zasób",
                definition="Puste lokale, długi czas remontu lokali odzyskanych, niska rotacja, niedopasowanie lokali do gospodarstw.",
                exclude=""),
    "P12": dict(name="Rynek najmu i najem krótkoterminowy",
                definition="Niewystarczająca oferta najmu, wysokie czynsze rynkowe, najem krótkoterminowy, popyt inwestycyjny.",
                exclude=""),
    "P13": dict(name="Zarządzanie, dane i zdolności instytucjonalne",
                definition="Brak polityki/danych/monitoringu mieszkaniowego, rozproszenie kompetencji, ograniczone środki i grunty gminy.",
                exclude=""),
    "P14": dict(name="Jakość otoczenia i segregacja przestrzenna",
                definition="Koncentracja problemów społecznych w zasobie komunalnym/osiedlach, niska jakość przestrzeni wspólnych, bezpieczeństwo.",
                exclude=""),
    "P99": dict(name="Inny problem mieszkaniowy",
                definition="Problem mieszkaniowy niemieszczący się w P01–P14 (opisz w polu statement).", exclude=""),
}

# ------------------------------------------------------------------ INSTRUMENTY (działania) -> RQ2, RQ4, RQ5
FAMILIES: dict[str, str] = {
    "F1": "Zwiększanie zasobu (podaż)",
    "F2": "Jakość i stan zasobu",
    "F3": "Kierowanie wsparcia (alokacja)",
    "F4": "Wsparcie finansowe najemców",
    "F5": "Zarządzanie zasobem",
    "F6": "Planowanie, regulacja, monitoring",
    "F7": "Finansowanie zewnętrzne i współpraca",
}
INSTRUMENTS: dict[str, dict] = {
    "I01": dict(family="F1", name="Budowa mieszkań komunalnych/socjalnych przez gminę", definition="Inwestycje gminy lub jej jednostek w nowe lokale komunalne/socjalne."),
    "I02": dict(family="F1", name="Budowa/rozwój TBS lub SIM", definition="Mieszkania czynszowe społeczne realizowane przez TBS/SIM/KZN, także dokapitalizowanie."),
    "I03": dict(family="F1", name="Zakup, pozyskanie lub adaptacja lokali i budynków", definition="Zakup lokali/budynków, przejęcie od Skarbu Państwa/spółdzielni, adaptacja pomieszczeń niemieszkalnych na mieszkania."),
    "I04": dict(family="F1", name="Najem od podmiotów prywatnych i podnajem", definition="Gmina wynajmuje lokale na rynku i podnajmuje (np. mieszkania wspierane, rodziny zastępcze)."),
    "I05": dict(family="F1", name="Polityka gruntowa i partnerstwa", definition="Grunty gminne pod mieszkalnictwo, wkład gruntowy, współpraca z deweloperami/PPP."),
    "I06": dict(family="F2", name="Remonty i modernizacje zasobu", definition="Remonty bieżące i kapitalne, remonty pustostanów, wymiana instalacji, dachów, stolarki."),
    "I07": dict(family="F2", name="Termomodernizacja i likwidacja źródeł niskosprawnych", definition="Docieplenia, likwidacja pieców węglowych, przyłączenia do sieci, OZE w budynkach."),
    "I08": dict(family="F2", name="Likwidacja zasobu substandardowego", definition="Rozbiórki, wykwaterowania, wyłączanie lokali z użytkowania, scalanie lokali niesamodzielnych."),
    "I09": dict(family="F2", name="Rewitalizacja obejmująca zasób mieszkaniowy", definition="Działania w ramach GPR dotyczące budynków/lokali mieszkalnych."),
    "I10": dict(family="F2", name="Dostosowanie lokali do potrzeb osób z niepełnosprawnościami", definition="Likwidacja barier, mieszkania dostępne, windy."),
    "I11": dict(family="F3", name="Kryteria przydziału i listy oczekujących", definition="Zasady najmu, komisje mieszkaniowe, listy, punktacja."),
    "I12": dict(family="F3", name="Najem socjalny, lokale zamienne, pomieszczenia tymczasowe i kryzysowe", definition="Realizacja obowiązków ustawowych wobec eksmitowanych i poszkodowanych."),
    "I13": dict(family="F3", name="Mieszkania chronione, wspierane, treningowe", definition="Formy mieszkalnictwa wspomaganego (także w zasobie MOPS)."),
    "I14": dict(family="F3", name="Wychodzenie z bezdomności i usamodzielnienie", definition="Housing First, programy dla opuszczających pieczę zastępczą, schroniska -> mieszkanie."),
    "I15": dict(family="F3", name="Mieszkania dla wybranych grup", definition="Oferta dla seniorów, młodych rodzin, nauczycieli/medyków, mieszkania służbowe."),
    "I16": dict(family="F4", name="Dodatki mieszkaniowe i energetyczne", definition="System dodatków (także dodatek energetyczny)."),
    "I17": dict(family="F4", name="Obniżki czynszu", definition="Dochodowe obniżki czynszu w zasobie gminy."),
    "I18": dict(family="F4", name="Restrukturyzacja i odpracowanie zadłużenia", definition="Ugody, raty, odpracowanie, programy osłonowe dla zadłużonych."),
    "I19": dict(family="F4", name="Dopłaty do czynszu/najmu", definition="Np. „Mieszkanie na start”, dopłaty finansowane z Funduszu Dopłat."),
    "I20": dict(family="F5", name="Zamiany lokali i racjonalizacja metrażu", definition="Biuro zamiany mieszkań, weryfikacja nadmetrażu, zamiany na mniejsze."),
    "I21": dict(family="F5", name="Sprzedaż lokali", definition="Sprzedaż najemcom/w przetargu, bonifikaty, wychodzenie ze wspólnot, albo decyzja o wstrzymaniu sprzedaży (koduj kierunek w polu stance)."),
    "I22": dict(family="F5", name="Polityka czynszowa i weryfikacja dochodów", definition="Stawki, strefy, podwyżki do % wartości odtworzeniowej, okresowa weryfikacja dochodów najemców."),
    "I23": dict(family="F5", name="Windykacja i poprawa ściągalności", definition="Procedury windykacyjne, wypowiedzenia, egzekucja."),
    "I24": dict(family="F5", name="Reorganizacja zarządzania i partycypacja najemców", definition="Zmiana formy zarządcy, zarządzanie partycypacyjne, cyfryzacja, wzmacnianie sprawczości najemców."),
    "I25": dict(family="F6", name="Planowanie przestrzenne pod zabudowę mieszkaniową", definition="Studium/mpzp, tereny inwestycyjne, uzbrojenie terenów dla mieszkalnictwa."),
    "I26": dict(family="F6", name="Regulacja i monitoring rynku, badania potrzeb", definition="Obserwatorium, badania potrzeb, regulacja najmu krótkoterminowego."),
    "I27": dict(family="F6", name="Program/polityka mieszkaniowa jako dokument dziedzinowy", definition="Zapowiedź lub realizacja odrębnego programu/polityki mieszkaniowej, aktualizacja WPGMZ."),
    "I28": dict(family="F7", name="Pozyskiwanie środków zewnętrznych", definition="BGK/Fundusz Dopłat, FRKF, KPO, fundusze UE, NFOŚiGW."),
    "I29": dict(family="F7", name="Współpraca z NGO, spółdzielniami, wspólnotami", definition="Partnerstwa, dofinansowanie remontów we wspólnotach, współpraca z organizacjami."),
    "I99": dict(family="F7", name="Inny instrument", definition="Instrument niemieszczący się w I01–I29 (opisz w polu description)."),
}

# ------------------------------------------------------------------ CROSSWALK problem -> instrumenty „adresujące” (hipoteza robocza, RQ4)
CROSSWALK: dict[str, list[str]] = {
    "P01": ["I01", "I02", "I03", "I04", "I05", "I19", "I25", "I28"],
    "P02": ["I06", "I08", "I09", "I28", "I29"],
    "P03": ["I06", "I08", "I20"],
    "P04": ["I07", "I09", "I28"],
    "P05": ["I01", "I02", "I03", "I04", "I12", "I28"],
    "P06": ["I12", "I13", "I14"],
    "P07": ["I17", "I18", "I22", "I23", "I24"],
    "P08": ["I10", "I13", "I15", "I19", "I02"],
    "P09": ["I05", "I15", "I25"],
    "P10": ["I09", "I25", "I08", "I05"],
    "P11": ["I06", "I20", "I03"],
    "P12": ["I02", "I04", "I19", "I26"],
    "P13": ["I24", "I26", "I27", "I28"],
    "P14": ["I09", "I24", "I29"],
    "P99": [],
}

GROUPS = ["low_income", "seniors", "disabled", "young_adults_families", "large_families", "homeless",
          "care_leavers", "evicted", "key_workers", "crisis_victims", "refugees_migrants", "general_population"]

# ------------------------------------------------------------------ Skala konkretności działania (0–5), addytywna
SPECIFICITY_RULE = (
    "Konkretność działania (0–5): 1 = ogólna deklaracja bez nazwanego instrumentu; 2 = nazwany instrument; "
    "+1 jeśli podana wartość docelowa lub skala (liczba lokali, budynków, osób); "
    "+1 jeśli podany budżet lub źródło finansowania; +1 jeśli podany termin lub podmiot odpowiedzialny. Maksimum 5."
)

# ------------------------------------------------------------------ Elementy ustawowe WPGMZ (art. 21 ust. 2 ustawy o ochronie praw lokatorów)
WPGMZ_ELEMENTS: dict[str, str] = {
    "E1": "Prognoza wielkości i stanu technicznego zasobu",
    "E2": "Analiza potrzeb oraz plan remontów i modernizacji",
    "E3": "Planowana sprzedaż lokali",
    "E4": "Zasady polityki czynszowej i warunki obniżania czynszu",
    "E5": "Sposób i zasady zarządzania zasobem; zmiany w zarządzaniu",
    "E6": "Źródła finansowania gospodarki mieszkaniowej",
    "E7": "Wysokość kosztów (eksploatacja, remonty, modernizacje, zarząd wspólnotami, inwestycje)",
    "E8": "Opis innych działań (zamiany, racjonalizacja, zwiększenie zasobu)",
}
