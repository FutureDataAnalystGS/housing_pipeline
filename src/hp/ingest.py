"""Etap 1. Ekstrakcja tekstu strona po stronie + diagnostyka jakości + OCR awaryjny.

Dlaczego nie wystarczy „pdftotext”: w próbce Biała Podlaska ma 28 stron, ale tylko strona 1 ma warstwę
tekstową; na stronach 2–28 tekst jest zapisany jako wektorowe kontury glifów (brak obrazów, brak tekstu),
a jedyny „tekst” to nagłówek Dziennika Urzędowego. Test „czy PDF ma obrazy” albo „czy pdffonts coś zwraca”
daje tu fałszywe wyniki. Dlatego oceniamy liczbę znaków UŻYTECZNYCH (po usunięciu powtarzalnych nagłówków).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

PL = "A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż"


@dataclass
class Page:
    doc_id: str
    page: int                 # numer strony PDF, od 1
    text: str
    method: str               # "text" | "ocr"
    raw_chars: int
    usable_chars: int
    ocr_conf: float | None = None
    flags: list[str] = field(default_factory=list)


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_key(s: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", s.strip().lower()))


def detect_boilerplate(doc: pymupdf.Document, zone: float = 0.09, min_share: float = 0.25) -> set[str]:
    """Powtarzalne bloki w górnym/dolnym marginesie (nagłówki, stopki, numery stron)."""
    counts: Counter[str] = Counter()
    n = len(doc)
    for page in doc:
        h = page.rect.height
        seen = set()
        for x0, y0, x1, y1, txt, *_ in page.get_text("blocks"):
            if y1 < h * zone or y0 > h * (1 - zone):
                k = _norm_key(txt)
                if k and k not in seen:
                    seen.add(k)
                    counts[k] += 1
    thr = max(3, int(min_share * n))
    return {k for k, c in counts.items() if c >= thr}


def page_text_without_boilerplate(page: pymupdf.Page, boiler: set[str]) -> str:
    """Tekst strony złożony z bloków (zachowuje akapity), z pominięciem nagłówków/stopek."""
    out = []
    for x0, y0, x1, y1, txt, bno, btype in page.get_text("blocks", sort=True):
        if btype != 0:
            continue
        if _norm_key(txt) in boiler:
            continue
        out.append(txt.strip())
    return "\n\n".join(t for t in out if t)


def _broken_encoding(text: str) -> bool:
    if not text:
        return False
    bad = sum(1 for ch in text if ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff")
    return bad / max(len(text), 1) > 0.02


def ocr_page(page: pymupdf.Page, lang: str = "pol", dpi: int = 250, tessdata: str | None = None) -> tuple[str, float | None]:
    """OCR jednej strony (rasteryzacja PyMuPDF -> tesseract). Zwraca (tekst, średnia pewność 0–100)."""
    if shutil.which("tesseract") is None:
        raise RuntimeError("Brak tesseract w PATH (zainstaluj tesseract-ocr i pakiet językowy 'pol').")
    env = os.environ.copy()
    if tessdata:
        env["TESSDATA_PREFIX"] = tessdata
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        page.get_pixmap(dpi=dpi).save(png)
        base = Path(td) / "o"
        subprocess.run(["tesseract", str(png), str(base), "-l", lang, "--psm", "4",
                        "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1"],
                       check=True, capture_output=True, env=env)
        text = (base.with_suffix(".txt")).read_text(encoding="utf-8", errors="ignore")
        confs = []
        for line in (base.with_suffix(".tsv")).read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 12 and parts[11].strip():
                try:
                    c = float(parts[10])
                    if c >= 0:
                        confs.append(c)
                except ValueError:
                    pass
    # typowe błędy OCR w dokumentach prawnych: „§” -> „$”, „ust.l” -> „ust.1”
    text = re.sub(r"(?<![\w$])\$\s*(\d+)", r"§ \1", text)
    text = re.sub(r"(?<=ust\.)l\b", "1", text)
    return text, (sum(confs) / len(confs) if confs else None)


def ingest_document(path: str | Path, doc_id: str, out_dir: str | Path, *, ocr: bool = True,
                    min_usable_chars: int = 120, lang: str = "pol", dpi: int = 250,
                    tessdata: str | None = None, max_ocr_pages: int | None = None) -> dict:
    """Zapisuje out_dir/<doc_id>.pages.jsonl i zwraca raport jakości dokumentu."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(path)
    boiler = detect_boilerplate(doc)
    pages: list[Page] = []
    n_ocr = 0
    for i, p in enumerate(doc, start=1):
        raw = p.get_text()
        txt = page_text_without_boilerplate(p, boiler)
        flags: list[str] = []
        n_graphics = 0
        usable = len(re.sub(r"\s+", "", txt))
        suspicious = usable < min_usable_chars
        if _broken_encoding(raw):
            flags.append("broken_encoding")
            suspicious = True
        if suspicious:
            n_graphics = len(p.get_drawings()) + len(p.get_images())
            if n_graphics > 50:
                flags.append("vector_or_raster_text_suspected")
            else:
                flags.append("near_empty_page")
        method, conf = "text", None
        if suspicious and ocr and n_graphics > 50:
            if max_ocr_pages is None or n_ocr < max_ocr_pages:
                txt, conf = ocr_page(p, lang=lang, dpi=dpi, tessdata=tessdata)
                method = "ocr"
                n_ocr += 1
                usable = len(re.sub(r"\s+", "", txt))
                if conf is not None and conf < 70:
                    flags.append("low_ocr_confidence")
        pages.append(Page(doc_id, i, txt, method, len(raw), usable, conf, flags))
    with open(out_dir / f"{doc_id}.pages.jsonl", "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(asdict(pg), ensure_ascii=False) + "\n")
    usable_pages = sum(1 for pg in pages if pg.usable_chars >= min_usable_chars)
    return dict(doc_id=doc_id, sha256=sha256(path), n_pages=len(pages), n_ocr_pages=n_ocr,
                n_unusable_pages=len(pages) - usable_pages, usable_chars=sum(pg.usable_chars for pg in pages),
                boilerplate_patterns=len(boiler), needs_review=(len(pages) - usable_pages) / max(len(pages), 1) > 0.15)


def load_pages(doc_id: str, interim_dir: str | Path) -> list[Page]:
    with open(Path(interim_dir) / f"{doc_id}.pages.jsonl", encoding="utf-8") as f:
        return [Page(**json.loads(line)) for line in f]


def normalize_for_search(text: str) -> str:
    """Normalizacja pod dopasowania: usuwa dzielenie wyrazów na końcu wiersza, ujednolica białe znaki i myślniki."""
    t = re.sub(rf"([{PL}]{{2,}})-\s*\n\s*([{PL}]{{2,}})", r"\1\2", text)
    t = re.sub(rf"([{PL}]{{2,}})-\s+([a-ząćęłńóśźż]{{3,}})", r"\1\2", t)  # „in- tensywnej”
    t = t.replace("\u00ad", "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip()
