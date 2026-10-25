"""Etap 3. Segmentacja.
 WPGMZ  -> sekcje wg ośmiu elementów ustawowych (E1–E8) metodą regułową (nagłówki „Rozdział…”), z awaryjnym trybem „cały dokument”.
 SR     -> wyszukiwanie akapitów o mieszkalnictwie (lexicon.score) wraz z kontekstem; zwraca pasaże ze stronami.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import lexicon
from .ingest import Page, normalize_for_search

# Wzorce w ASCII: nagłówek jest składany przez fold_pl(), więc OCR-owe „Zródła” (zamiast „Źródła”) też działa.
ELEMENT_RULES: dict[str, str] = {
    "E1": r"prognoz\w+.*(?:wielko|stan\w*\s+technicz)|wielko\w+\s+oraz\s+stan\w*\s+technicz|wielkosc\s+i\s+stan\s+technicz",
    "E2": r"analiz\w+\s+potrzeb|plan\w*\s+remont|remont\w+\s+i\s+modernizacj",
    "E3": r"planowan\w+\s+sprzedaz|sprzedaz\w*\s+lokali",
    "E4": r"polityk\w+\s+czynszow|obnizan\w+\s+czynszu|warunk\w+\s+obniz",
    "E5": r"sposob\s+i\s+zasady\s+zarzadzani|zarzadzani\w+\s+lokalami",
    "E6": r"zrodl\w+\s+finansowani",
    "E7": r"wysokosc\s+(?:kosztow|wydatkow)|koszt\w+\s+biezacej\s+eksploatacji",
    "E8": r"opis\s+innych\s+dzialan|racjonalizacj\w+\s+gospodarowani|poprawe\s+wykorzystania",
}
_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold_pl(s: str) -> str:
    return s.translate(_FOLD)


_ELEM = {k: re.compile(v, re.I | re.S) for k, v in ELEMENT_RULES.items()}
HEAD = re.compile(r"^\s*(?:ROZDZIAŁ|Rozdział)\s+([IVXLC]+|\d+)\.?\s*[-–—.:]?\s*(.*)$")


@dataclass
class Section:
    element: str | None
    title: str
    page_start: int
    page_end: int
    text: str


def _lines_with_pages(pages: list[Page]) -> list[tuple[int, str]]:
    out = []
    for pg in pages:
        for ln in pg.text.split("\n"):
            if ln.strip():
                out.append((pg.page, ln.strip()))
    return out


TOC_LINE = re.compile(r"\.{4,}|\s\d{1,3}\s*$")   # kropki wiodące lub numer strony na końcu = wpis spisu treści


def _render(slice_: list[tuple[int, str]]) -> str:
    out, cur = [], None
    for pg, ln in slice_:
        if pg != cur:
            out.append(f"[[strona {pg}]]")
            cur = pg
        out.append(ln)
    return "\n".join(out)


def classify_heading(heading_text: str) -> str | None:
    heading_text = fold_pl(heading_text)
    best, best_len = None, 0
    for el, rx in _ELEM.items():
        m = rx.search(heading_text)
        if m and len(m.group(0)) > best_len:
            best, best_len = el, len(m.group(0))
    return best


def segment_wpgmz(pages: list[Page], min_chars: int = 400) -> list[Section]:
    lines = _lines_with_pages(pages)
    starts: list[tuple[int, int, str]] = []   # (indeks wiersza, strona, tytuł)
    for i, (pg, ln) in enumerate(lines):
        m = HEAD.match(ln)
        if not m:
            continue
        title = m.group(2).strip()
        if TOC_LINE.search(m.group(2)):
            continue                                   # wpis spisu treści, nie nagłówek
        j = i + 1
        while len(title) < 220 and j < len(lines) and j <= i + 4 and not lines[j][1].startswith("§") \
                and not re.match(r"^\d+[.)]\s", lines[j][1]) and not HEAD.match(lines[j][1]):
            title += " " + lines[j][1]
            j += 1
        starts.append((i, pg, title))
    sections: list[Section] = []
    for k, (i, pg, title) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = _render(lines[i:end])
        page_end = lines[end - 1][0] if end > i else pg
        sections.append(Section(classify_heading(title), title[:240], pg, page_end, body))
    # odrzucamy wpisy ze spisu treści (krótkie „sekcje”)
    sections = [s for s in sections if len(s.text) >= min_chars]
    return _last_run(sections)


def _last_run(sections: list[Section]) -> list[Section]:
    """Spis treści daje pierwszy „bieg” elementów E1..E8, właściwy tekst — drugi. Gdy kolejność elementów
    się „cofa” (np. E8 -> E1), zaczyna się nowy bieg; zostawiamy ostatni, który ma >=4 różne elementy."""
    runs: list[list[Section]] = [[]]
    last_rank = 0
    for s in sections:
        rank = int(s.element[1:]) if s.element else last_rank
        if rank < last_rank:
            runs.append([])
        runs[-1].append(s)
        last_rank = rank or last_rank
    good = [r for r in runs if len({x.element for x in r if x.element}) >= 4]
    return good[-1] if good and len(runs) > 1 else sections


def element_texts(sections: list[Section]) -> dict[str, str]:
    d: dict[str, list[str]] = {}
    for s in sections:
        if s.element:
            d.setdefault(s.element, []).append(s.text)
    return {k: "\n\n".join(v) for k, v in d.items()}


def segmentation_report(sections: list[Section]) -> dict:
    found = sorted({s.element for s in sections if s.element})
    return dict(n_sections=len(sections), elements_found=found,
                elements_missing=[e for e in ELEMENT_RULES if e not in found],
                fallback_full_text=len(found) < 5)


# ------------------------------------------------------------------ strategie
@dataclass
class Passage:
    page_start: int
    page_end: int
    score: float
    text: str


def retrieve_passages(pages: list[Page], min_score: float = 1.0, context: int = 1, max_chars: int = 90000) -> list[Passage]:
    """Akapity (bloki tekstu) ocenione słownikiem; łączymy trafne akapity z sąsiadami. Zwraca pasaże wg kolejności w dokumencie."""
    units: list[tuple[int, str, float]] = []
    for pg in pages:
        buf = ""
        for blk in re.split(r"\n\s*\n", pg.text):
            blk = normalize_for_search(blk)
            if not blk:
                continue
            buf = (buf + " " + blk).strip()
            if len(buf) >= 350:
                units.append((pg.page, buf, lexicon.score(buf)))
                buf = ""
        if len(buf) > 40:
            units.append((pg.page, buf, lexicon.score(buf)))
    keep = [False] * len(units)
    # priorytet RECALL: wystarczy jeden mocny termin w jednostce; precyzję zapewnia późniejsze kodowanie (pole relevant)
    for i in range(len(units)):
        if units[i][2] >= min_score:
            for j in range(max(0, i - context), min(len(units), i + context + 1)):
                keep[j] = True
    passages: list[Passage] = []
    cur: list[tuple[int, str, float]] = []
    for i, k in enumerate(keep):
        if k:
            cur.append(units[i])
        elif cur:
            passages.append(_pack(cur)); cur = []
    if cur:
        passages.append(_pack(cur))
    total = 0
    out = []
    for p in sorted(passages, key=lambda x: -x.score):      # przy limicie zostają najtrafniejsze
        if total + len(p.text) > max_chars:
            continue
        out.append(p); total += len(p.text)
    return sorted(out, key=lambda x: x.page_start)


def _pack(cur):
    parts, last = [], None
    for pg, txt, _ in cur:
        if pg != last:
            parts.append(f"[[strona {pg}]]")
            last = pg
        parts.append(txt)
    return Passage(cur[0][0], cur[-1][0], sum(u[2] for u in cur), "\n\n".join(parts))
