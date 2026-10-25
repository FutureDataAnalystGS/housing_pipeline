# Pipeline analizy lokalnej polityki mieszkaniowej (strategie rozwoju + WPGMZ)

Analiza treści 2 × 66 dokumentów miast na prawach powiatu: **diagnoza** (problemy, zasób, stan lokali) i **działania** (cele, instrumenty, nakłady).
Kodowanie wspomagane LLM z pełnym śladem dowodowym (strona + cytat), walidacją programową i podwójnym kodowaniem próby przez człowieka.

## Szybki start
```bash
pip install -r requirements.txt
sudo apt install tesseract-ocr tesseract-ocr-pol          # OCR skanów (lub ocrmypdf)
export ANTHROPIC_API_KEY=...                              # tylko etap `extract` i streszczenia LLM
# 1. PDF-y do data/raw/ ; nazwy: WPGMZ_<miasto>_<okres>.pdf, SR_<miasto>_<okres>.pdf
PYTHONPATH=src python -m hp.cli inventory                 # tworzy data/registry.csv -> uzupełnij city_id (TERYT), miasto, województwo, URL
PYTHONPATH=src python -m hp.cli ingest                    # tekst per strona + diagnostyka + OCR awaryjny
PYTHONPATH=src python -m hp.cli metadata                  # uchwała, daty, okres, nowelizacje (flagi do przeglądu)
PYTHONPATH=src python -m hp.cli segment                   # WPGMZ: elementy E1–E8; SR: pasaże o mieszkalnictwie
PYTHONPATH=src python -m hp.cli extract --doc WPGMZ_gdynia_2022-2026   # najpierw 1 dokument, potem całość
PYTHONPATH=src python -m hp.cli validate && PYTHONPATH=src python -m hp.cli aggregate
PYTHONPATH=src python -m hp.cli analyze [--k 4]           # skan k (silhouette + stabilność), typologia
PYTHONPATH=src python -m hp.cli report                    # karty/streszczenia dokumentów
PYTHONPATH=src python -m hp.cli codebook                  # codebook/codebook.xlsx z schema.py + taxonomy.py
python -m pytest tests -q                                 # testy łańcucha bez API
```

## Struktura
| Plik | Rola |
|---|---|
| `taxonomy.py` | Słowniki: problemy P01–P99, instrumenty I01–I99, rodziny F1–F7, crosswalk, skale — **źródło prawdy księgi kodowej** |
| `schema.py` | Zmienne dokumentów jako modele Pydantic (opisy = definicje) → schematy JSON dla LLM i arkusz kodowy |
| `ingest.py` | Ekstrakcja tekstu per strona; usuwanie nagłówków/stopek; wykrywanie stron bez użytecznego tekstu (także wektorowych); OCR `pol` |
| `metadata.py` | Numer i data uchwały, okres, nowelizacje; daty nieistniejące w kalendarzu są flagowane, nie poprawiane |
| `segment.py` | WPGMZ → 8 elementów ustawowych (odporna na spis treści i błędy OCR); SR → wyszukiwanie fragmentów (słownik, nastawiony na recall) |
| `lexicon.py` | Terminy „polityczne” vs „przestrzenne” (zabudowa mieszkaniowa ≠ polityka mieszkaniowa); benchmark słownikowy |
| `extract_llm.py` | Wymuszone wywołanie narzędzia (JSON), cache, ponowienie po błędzie walidacji, weryfikacja cytatów |
| `validate.py` | Spójność: sumy zasobu, bilans prognozy, daty, zakresy, brak dowodów |
| `aggregate.py` | Tabele szerokie/długie, wskaźniki (lokale/1000 mieszk., zmiana zasobu, sprzedaż %/rok, pokrycie kosztów…), indeks pokrycia diagnozy działaniami |
| `analysis.py` | Odległość Gowera, klasteryzacja, silhouette, stabilność (ARI), profile typów |
| `summarize.py` | Karta dokumentu (deterministyczna) i streszczenie LLM z zakodowanych pól |

## Rejestr `data/registry.csv`
`doc_id, file, doc_type (SR|WPGMZ), city_id (TERYT), city, voivodeship, source_url, notes` + (dla SR) data uchwalenia i numer uchwały z BIP, bo plik strategii zwykle ich nie zawiera.
Dane zewnętrzne: `data/external/bdl.csv` (`city_id, population, …` z BDL GUS) — do normalizacji zasobu.

## Protokół jakości (przed uruchomieniem na całym korpusie)
1. **Pilotaż** na 8–10 dokumentach (zróżnicowane: skan, duże/małe miasto, nowelizacja) → poprawki księgi kodowej → zamrożenie wersji (v1.0) i `prompt_version`.
2. **Podwójne kodowanie ręczne** próby ≈ 20% (≥ 13 WPGMZ + 13 SR, losowanie warstwowane) w arkuszu `Arkusz_dwoch_kodujacych`; zgodność kodujących (α Krippendorffa / κ) i zgodność LLM–wzorzec (precision/recall per zmienna); progi: κ/α ≥ 0,7 dla kategorii, ≥ 95% dla liczb.
3. **Recall wyszukiwania fragmentów w SR**: na 10 strategiach porównaj wynik z czytaniem wyczerpującym (cały tekst w kawałkach); przyjmij retrieval, gdy recall pozycji ≥ 95%.
4. Wszystkie flagi `validate.py` o poziomie `error` przechodzą przegląd ręczny; wynik przeglądu zapisywany osobno (nie nadpisuje surowych odpowiedzi LLM).
5. Raportuj: wersję księgi, model, datę uruchomienia, odsetek zweryfikowanych cytatów, odsetek stron OCR.

## Znane ograniczenia (z pilotażu na 6 plikach)
* Skany/wektorowe PDF-y (Biała Podlaska: 27 z 28 stron) wymagają OCR; OCR psuje `§`, cyfry i tabele — liczby z tabel w skanach weryfikuj z obrazem strony.
* Definicje „zasobu” różnią się między miastami (czy wliczone lokale we wspólnotach, TBS, spółdzielnie) → zmienne W1 kodowane jak w dokumencie, porównania po normalizacji i z uwzględnieniem struktury własności.
* Daty odniesienia danych różnią się (31.12.2020 vs 30.09.2021) i zdarzają się błędy w dokumentach (np. „31.09.2021”).
* LLM-owa ekstrakcja NIE była uruchomiona na żywo w pilotażu (brak klucza API w środowisku); łańcuch przetestowano na ręcznie zakodowanych rekordach (`tests/fixtures.py`).
