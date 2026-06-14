# Task: Scraper Agent — Data Miner

**Branch:** `feature/scraper-justjoin` (potem `feature/scraper-pracuj`, `feature/scraper-linkedin`)  
**Moduły:** `src/job_search/scrapers/`  
**Priorytet:** P1 (po gotowości memory upsert)

---

## Cel

Implementacja scraperów pobierających oferty pracy z portali dla sektorów **Data** i **Automatyka**, z normalizacją do schematu `JobOfferCreate`.

---

## Mapowanie sektorów → słowa kluczowe

### Data (`JobSector.DATA`)
| Portal | Zapytania / kategorie |
|--------|----------------------|
| JustJoin.it | `data`, `analytics`, `data-science` |
| Pracuj.pl | „Data Analyst”, „Data Engineer”, „Data Scientist” |
| LinkedIn | job title filters |

### Automatyka (`JobSector.AUTOMATION`)
| Portal | Zapytania / kategorie |
|--------|----------------------|
| JustJoin.it | `automation`, `plc`, `scada` |
| Pracuj.pl | „Automatyk”, „Programista PLC”, „Inżynier automatyki” |
| LinkedIn | job title filters |

---

## Zakres prac — Faza 1: JustJoin.it

JustJoin.it udostępnia publiczne API — **preferuj API nad scraping HTML**.

### 1. Implementacja `JustJoinScraper`

Plik: `scrapers/sources/justjoin.py`

- [ ] Endpoint: `GET {JUSTJOIN_API_BASE}/offers` z filtrami kategorii.
- [ ] Mapowanie odpowiedzi JSON → `JobOfferCreate`:
  - `external_id` ← `id` lub slug oferty
  - `source` ← `"justjoin"`
  - `skills` ← tablica skilli z API
  - `salary_min/max` ← parsowanie widełek
  - `remote` ← pole remote/hybrid
- [ ] Obsługa paginacji i rate limiting (`SCRAPER_REQUEST_DELAY_SECONDS`).
- [ ] `health_check()` — HEAD/GET na API, status 200.

### 2. Wspólna infrastruktura scraperów

Nowy plik: `scrapers/http_client.py`

- [ ] Wrapper `httpx.Client` z retry (tenacity), user-agent z settings.
- [ ] Logowanie błędów do `structlog`.

Nowy plik: `scrapers/registry.py`

- [ ] Rejestr scraperów: `get_scrapers() -> list[BaseScraper]`.
- [ ] Factory `run_scraper(source, sector) -> ScraperResult`.

### 3. Integracja z Memory

- [ ] Po każdym `fetch_offers()` — wywołanie `JobOfferRepository.upsert()` dla każdej oferty.
- [ ] Rejestrowanie `ScrapeRun` (start/finish, liczniki).
- [ ] CLI: `python -m job_search.cli scrape --source justjoin --sector data`.

### 4. Testy

- [ ] Mock httpx responses (`tests/fixtures/justjoin_sample.json`).
- [ ] Test mapowania JSON → `JobOfferCreate`.
- [ ] Test obsługi pustej odpowiedzi API.

---

## Zakres prac — Faza 2: Pracuj.pl

- [ ] Analiza struktury HTML listingu ofert.
- [ ] BeautifulSoup parser lub Selenium (jeśli JS-rendered).
- [ ] Szczegóły oferty: osobne żądanie HTTP per URL.
- [ ] **Uwaga prawna:** respektuj `robots.txt`, dodaj opóźnienia między requestami.

---

## Zakres prac — Faza 3: LinkedIn

- [ ] LinkedIn wymaga uwierzytelnienia — rozważ oficjalne API lub scraper z sesją użytkownika.
- [ ] Udokumentuj w README wymagane cookies / tokeny w `.env`.
- [ ] Oznacz moduł jako opcjonalny (`LINKEDIN_ENABLED=false` domyślnie).

---

## Definition of Done (Faza 1)

- `JustJoinScraper.fetch_offers(JobSector.DATA)` zwraca ≥1 ofertę w dev.
- Oferty trafiają do SQLite via `upsert`.
- `ScrapeRun` rejestruje statystyki.
- Testy jednostkowe przechodzą bez live API (mocki).

---

## Pliki do edycji / utworzenia

```
src/job_search/scrapers/http_client.py     (NOWY)
src/job_search/scrapers/registry.py        (NOWY)
src/job_search/scrapers/sources/justjoin.py
src/job_search/scrapers/sources/pracuj_pl.py
src/job_search/scrapers/sources/linkedin.py
tests/fixtures/justjoin_sample.json        (NOWY)
tests/test_justjoin_scraper.py             (NOWY)
```

---

## Kontrakt z innymi modułami

```python
# Scraper MUSI zwracać:
ScraperResult(
    source="justjoin",
    sector=JobSector.DATA,
    offers=[JobOfferCreate(...), ...],
    errors=[],
)
```

Memory Agent zajmuje się persystencją — scraper **nie zapisuje** bezpośrednio do DB (Separation of Concerns), chyba że orchestrator tak zdecyduje.

---

## Przykładowe polecenie

```bash
pytest tests/test_justjoin_scraper.py -v
python -m job_search.cli scrape --source justjoin --sector data  # po implementacji CLI
```
