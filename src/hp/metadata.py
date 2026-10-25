"""Etap 2. Metadane dokumentu (reguły + walidacja dat). Pola niepewne dostają needs_review=True."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {"stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6, "lipca": 7,
          "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12}
_MON = "|".join(MONTHS)
DATE_TXT = re.compile(rf"(\d{{1,2}})\s+({_MON})\s+(\d{{4}})")
DATE_NUM = re.compile(r"(\d{1,2})[.](\d{1,2})[.](\d{4})")


def parse_date(s: str | None) -> str | None:
    """Zwraca ISO (YYYY-MM-DD) albo None; nieistniejące daty (np. 31.09.2021) NIE są poprawiane."""
    if not s:
        return None
    m = DATE_TXT.search(s)
    if m:
        d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    else:
        m = DATE_NUM.search(s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def extract_metadata(pages_text: list[str], doc_type: str) -> dict:
    """pages_text: lista tekstów stron. doc_type: 'WPGMZ' | 'SR'."""
    head = _flat(" ".join(pages_text[:4]))
    whole = _flat(" ".join(pages_text))
    md: dict = dict(doc_type=doc_type, resolution_number=None, adoption_date=None, council=None,
                    publication_journal=None, publication_date=None, publication_pos=None,
                    period_start=None, period_end=None, is_amendment=False, amends_number=None,
                    amends_date=None, replaces_number=None, needs_review=[])

    m = re.search(r"UCHWA[ŁL]A\s+(?:NR|Nr|nr)\s+([A-Za-z0-9./\-]+)", head)
    if m:
        md["resolution_number"] = m.group(1).strip(".")
        m2 = re.search(r"z\s+dnia\s+(\d{1,2}\s+\w+\s+\d{4})", head[m.end():m.end() + 200])
        md["adoption_date"] = parse_date(m2.group(1)) if m2 else None
    m = re.search(r"RADY\s+MIAST[AO]\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ\- ]+?)\s+(?:z\s+dnia|w\s+sprawie)", head)
    if m:
        md["council"] = m.group(1).title()

    m = re.search(r"DZIENNIK\s+URZĘDOWY\s+(WOJEWÓDZTWA\s+[A-ZĄĆĘŁŃÓŚŹŻ\-]+)", head)
    if m:
        md["publication_journal"] = "Dz. Urz. " + m.group(1).title().replace("Województwa", "Woj.")
        m2 = re.search(r"[A-ZŁŚŻŹ][a-ząćęłńóśźż]+,\s+dnia\s+(\d{1,2}\s+\w+\s+\d{4})", head)
        md["publication_date"] = parse_date(m2.group(1)) if m2 else None
    m = re.search(r"\bPoz\.\s*(\d+)", head)
    if m:
        md["publication_pos"] = int(m.group(1))

    # okres obowiązywania
    m = re.search(r"na\s+lata\s+(20\d\d)\s*[-–—]\s*(20\d\d)", head, re.I) or \
        re.search(r"w\s+latach\s+(20\d\d)\s*[-–—]\s*(20\d\d)", head, re.I)
    if m:
        md["period_start"], md["period_end"] = int(m.group(1)), int(m.group(2))
    elif doc_type == "SR":
        title_zone = _flat(" ".join(pages_text[:3]))
        cands = [int(x) for x in re.findall(r"(?:do|-|–|—)\s*(20[2-5]\d)\s*\+?", title_zone)]
        cands += [int(x) for x in re.findall(r"\b(20[2-5]\d)\s*\+", title_zone)]
        if cands:
            md["period_end"] = Counter_mode(cands)
        rng = re.search(r"(20[12]\d)\s*[-–—]\s*(20[2-5]\d)", title_zone)
        if rng:
            md["period_start"], md["period_end"] = int(rng.group(1)), int(rng.group(2))

    if doc_type == "SR" and not md["resolution_number"]:
        zone = _flat(" ".join(pages_text[:6] + pages_text[-6:]))
        r = re.search(r"[Uu]chwa[łl]\w*\s+(?:Nr|nr|NR)\s+([A-Za-z0-9./\-]+)\s+Rady\s+Miast\w*\s+[^.]{0,60}?z\s+dnia\s+(\d{1,2}\s+\w+\s+\d{4})", zone)
        if r:
            md["resolution_number"], md["adoption_date"] = r.group(1), parse_date(r.group(2))

    # nowelizacja / uchylenie poprzedniej uchwały
    if re.search(r"w\s+sprawie\s+zmiany\s+uchwały|Zmienia\s+się\s+uchwałę", head, re.I):
        md["is_amendment"] = True
        m = re.search(r"Zmienia\s+się\s+uchwałę\s+(?:Nr\s+)?([A-Za-z0-9./\-]+)\s+Rady\s+Miast\w*\s+.+?\s+z\s+dnia\s+(\d{1,2}\s+\w+\s+\d{4})", head)
        if m:
            md["amends_number"], md["amends_date"] = m.group(1), parse_date(m.group(2))
    m = re.search(r"Traci\s+moc\s+uchwała\s+Nr\s+([A-Za-z0-9./\-]+)", head)
    if m:
        md["replaces_number"] = m.group(1)

    # kontrola jakości
    if doc_type == "WPGMZ" and not md["resolution_number"]:
        md["needs_review"].append("resolution_number")
    if not md["adoption_date"]:
        md["needs_review"].append("adoption_date")
    if md["period_end"] is None:
        md["needs_review"].append("period")
    if md["adoption_date"] and md["publication_date"] and md["publication_date"] < md["adoption_date"]:
        md["needs_review"].append("publication_before_adoption")
    return md


def Counter_mode(xs: list[int]) -> int:
    from collections import Counter
    return Counter(xs).most_common(1)[0][0]
