# Zmiany względem poprzedniej wersji (pod Ollamę, bez płatnego API)

## Dlaczego „nie wyszukuje problemów” — przyczyny znalezione w kodzie
1. **Ollama ucinała prompt.** Bez `num_ctx` Ollama używa 2048–4096 tokenów i po cichu odrzuca początek promptu (instrukcję), a 4 strony dokumentu to 8–12 tys. tokenów. Model dostawał urywek bez zadania i zwracał puste listy.
2. **Model nie znał kodów.** W Ollamie `format` (schemat JSON) działa tylko jak gramatyka wyjścia; model nie widzi opisów pól ani definicji P01–P99/I01–I99. Kody w `actions.csv` idą po kolei (I20, I21, I22…), czyli były losowe.
3. **`json_schema_extra={"type": "liczba"}` nadpisywało `"type": "object"` w schemacie** (stąd „BRAK TYPU” w `wynik_testu.txt`). W starym `inline_schema` kasowało to typ całkiem; model dostawał niepełną gramatykę.
4. **Pola były opcjonalne.** Przy opcjonalnych polach mały model „oszczędza” i zwraca prawie pusty JSON (w `docs.csv` brakuje kolumn liczbowych zasobu).
5. **`num_predict` przycięte do 2048** → ucięty JSON → wyjątek/powtórki.
6. **Puste `city_id` w rejestrze** → `city_indices.csv` i `alignment.csv` mają jeden pusty wiersz.

## Co zmieniono
| Plik | Zmiana |
|---|---|
| `ollama_client.py` (nowy) | `num_ctx`, `num_predict`, `seed` zawsze wysyłane; wykrywanie uciętej odpowiedzi i zbyt długiego promptu; digest modelu |
| `prompts.py` (nowy) | definicje P/I, zasady, 2 przykłady (jeden pusty) i opisy pól w prompcie |
| `schema.py` | `kind` zamiast `type`; wszystkie pola wymagane; etykiety „P05 Niedobór…” w gramatyce; odchudzone modele `Llm*`; kolejność pól: cytat → klasyfikacja |
| `extract_llm.py` | małe fragmenty (≈4,5 tys. zn.), jedno zadanie na wywołanie, podział fragmentu po błędzie, odrzucanie pozycji bez cytatu w dokumencie, korekta numeru strony, kontrola liczb względem cytatu, siatka bezpieczeństwa (słownik problemów) |
| `lexicon.py` | + `baseline_problems` |
| `aggregate.py` | zastępczy klucz miasta z `doc_id`; przeliczanie „tys. zł”/„mln zł” |
| `validate.py` | flagi: liczba bez pokrycia w cytacie, odrzucone pozycje, możliwe pominięcia, błędy LLM |
| `evaluate.py` (nowy) | ocena modelu względem ręcznego wzorca (`tests/fixtures.py`) |
| `check_ollama.py` (nowy) | diagnostyka: serwer, okno kontekstu, jeden prawdziwy fragment |
| `config.yaml` | sekcja `llm` pod Ollamę |
| `tests/test_ollama_mock.py` (nowy) | 7 testów mechaniki na atrapie serwera |

Wyłączone w wersji „odchudzonej” (zbyt zawodne dla małych modeli): `addresses_problems` i `link_explicit` w działaniach. RQ4 liczymy na razie przez crosswalk (`aggregate.alignment`); jawne powiązania można dodać osobnym, drugim przebiegiem.
