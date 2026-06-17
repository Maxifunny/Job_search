# Task: UI Agent — Streamlit Demo Panel

**Branch:** `cursor/ui-streamlit-*`  
**Moduły:** `ui/`, `scripts/run_ui.*`, `README.md`  
**Priorytet:** P2

---

## Cel

Dostarczyć prosty, czytelny interfejs Streamlit do prezentacji działania pipeline
osobom nietechnicznym.

UI ma pozwalać na:

1. wybór parametrów uruchomienia,
2. start pipeline jednym kliknięciem,
3. podgląd logów z uruchomienia,
4. przegląd statusu, rekomendacji i ofert z SQLite.

---

## Zakres

- `ui/app.py`
  - sidebar z ustawieniami (`sector`, `profile`, `source`, limity, sync_vectors),
  - przycisk `Uruchom pipeline`,
  - zakładki: `Status`, `Rekomendacje`, `Oferty`, `Logi/Diagnoza`,
  - ostrzeżenia przy braku `.env` lub `LLM_API_KEY`.

- `ui/data_access.py`
  - bezpieczny, read-only odczyt z SQLite,
  - helpery do list sektorów i profili,
  - kwerendy dla statusu/rekomendacji/ofert.

- skrypty uruchomieniowe:
  - `scripts/run_ui.sh`
  - `scripts/run_ui.ps1`

---

## Wymagania UX

- Polski język etykiet i komunikatów.
- Brak ekspozycji sekretów (API key nigdy nie jest wypisywany).
- Prosty układ: mniej opcji, więcej czytelności.
- Stabilność: UI nie może crashować przy pustej bazie / brakujących tabelach.

---

## Definition of Done

- `python3 -m streamlit run ui/app.py` startuje poprawnie.
- `python3 -m pytest tests/ -q` przechodzi.
- README ma sekcję „UI (Streamlit)” z instrukcją uruchomienia.
- Dodane testy helperów `ui/data_access.py` (czyste funkcje Python/SQLite).
