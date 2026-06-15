# Task: Pipeline Agent — Master / Orchestrator

**Branch:** `feature/pipeline-integration`
**Moduły:** `src/job_search/orchestrator/`, `src/job_search/cli.py` (komenda `run`)
**Priorytet:** P2 (po scalonych PR-ach Scraper + Matching)

---

## Cel

Połączyć gotowe moduły (`scrapers/`, `memory/`, `matching/`) w jeden autonomiczny
przepływ uruchamiany jedną komendą CLI:

```
SCRAPE → STORE → MATCH → RECOMMEND
```

Orchestrator **tylko koordynuje** — nie implementuje scrapingu ani logiki LLM.
Reużywa istniejących funkcji:

- `scrape_and_persist(sector, source=..., sync_vectors=..., **scrape_kwargs)` (scrapers)
- `match_pending_offers(profile, sector=..., limit=...)` (matching)

---

## Architektura

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ 1. SCRAPE   │ →  │ 2. STORE     │ →  │ 3. MATCH    │ →  │ 4. REPORT    │
│ scrapers    │    │ SQLite+Chroma│    │ LLM+semantic│    │ rekomendacje │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
```

| Krok | Wywołanie |
|------|-----------|
| 1+2  | `scrape_and_persist(sector, source=..., sync_vectors=True, **scrape_kwargs)` |
| 3    | `match_pending_offers(profile, sector=sector, limit=match_limit)` |
| 4    | zwróć `PipelineResult` z podsumowaniem + lista `recommendations` |

---

## `PipelineResult`

```python
@dataclass
class PipelineResult:
    sector: JobSector
    scraped: int = 0          # suma offers_found ze scrape
    new_offers: int = 0       # suma offers_new
    updated_offers: int = 0
    evaluated: int = 0        # z match summary
    accepted: int = 0
    rejected: int = 0
    skipped: int = 0
    recommendations: list[str] = []   # "title @ company — url"
    scrape_errors: list[str] = []
    errors: list[str] = []
```

## `JobSearchPipeline.run()`

```python
def run(
    self,
    sector: JobSector,
    profile: CandidateProfile,
    *,
    source: str | None = None,
    sync_vectors: bool = True,      # matching semantyczny wymaga embeddingów
    max_offers: int | None = None,
    max_pages: int | None = None,
    match_limit: int | None = None,
) -> PipelineResult: ...
```

### Obsługa błędów

- Błędy scrapera (np. Cloudflare na `pracuj.pl`) → trafiają do `scrape_errors`,
  matching i tak działa na ofertach już zapisanych w bazie.
- Pusty scrape (0 nowych ofert) → pipeline nie crashuje, uruchamia matching na
  istniejących ofertach w DB.
- `KeyboardInterrupt` → przechwytywany w CLI, komunikat „Przerwano pipeline”.
- Brak `LLM_API_KEY` → matching działa w trybie dev, wypisywane jest ostrzeżenie.

---

## CLI — `run`

```bash
python -m job_search.cli run --sector data --profile config/profiles/default.json
```

| Argument | Opis |
|----------|------|
| `--sector {data,automation}` | wymagany |
| `--profile PATH` | domyślnie `config/profiles/default.json` |
| `--source {justjoin,pracuj_pl,nofluffjobs}` | opcjonalny (domyślnie wszystkie) |
| `--max-offers INT` | limit scrapowania per portal |
| `--max-pages INT` | limit stron per portal |
| `--match-limit INT` | limit ofert do oceny LLM (oszczędność API) |
| `--no-sync-vectors` | pomiń ChromaDB przy scrape (tylko debug) |

### Przykładowy output

```
[pipeline] Krok 1/3: Scrapowanie ofert...
[justjoin] found=10 new=8 updated=2
[pipeline] Krok 2/3: Dopasowywanie ofert do profilu...
[data] evaluated=10 accepted=3 rejected=6 skipped=1
[pipeline] Krok 3/3: Gotowe.

=== REKOMENDACJE (3) ===
✅ Data Engineer @ Acme Corp — https://justjoin.it/offers/...
✅ Senior Data Analyst @ DataWorks — https://justjoin.it/offers/...
✅ ML Engineer @ NeoML — https://justjoin.it/offers/...
```

---

## Definition of Done

- `python -m job_search.cli run --sector data --profile config/profiles/default.json --max-offers 5 --match-limit 5`
  działa end-to-end (przy skonfigurowanym `.env`).
- `pytest tests/test_pipeline.py -v` przechodzi (mock scrape + match, bez live API).
- `pytest tests/ -v` — wszystkie testy projektu przechodzą.
- README zaktualizowany: status Pipeline = ✅, przykład komendy `run`.

---

## Pliki do edycji / utworzenia

```
src/job_search/orchestrator/pipeline.py
src/job_search/orchestrator/__init__.py
src/job_search/cli.py            (tylko komenda run)
tests/test_pipeline.py           (NOWY)
docs/agents/pipeline-agent.md    (NOWY)
README.md                        (sekcja CLI run + status)
```

## Zależności

- **Wymaga:** `scrape_and_persist` (Scraper Agent), `match_pending_offers` +
  `load_profile` (Matching Agent), `CandidateProfile`, `JobSector` ze `schemas/`.
- **Dostarcza:** komendę `run` — pełny autonomiczny przepływ systemu.
