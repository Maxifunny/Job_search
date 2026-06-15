# Profile / Sector Config Agent — Definition of Done

## Scope

Make job sectors configurable via JSON under `config/sectors/` so users can add professions without code changes.

## Deliverables

- [x] `config/sectors/data.json` — migrated Data queries + false-positive rules
- [x] `config/sectors/automation.json` — migrated Automation queries + false-positive rules
- [x] `config/sectors/example.json` — shareable template (backend developer)
- [x] `config/sector_loader.py` — `SectorConfig`, `load_sector_config`, `list_sector_ids`, `resolve_sector`, `queries_for_sector`
- [x] Alembic `002_sector_string.py` — `job_offers.sector` and `scrape_runs.sector` → `String(64)`
- [x] Scrapers read portal queries from sector config (no hardcoded `_default_queries`)
- [x] `FalsePositiveFilter` uses `SectorConfig` rules
- [x] CLI `--sector` choices from `list_sector_ids()`; new `list-sectors` subcommand
- [x] `config/profiles/example_backend.json` — shareable profile template
- [x] README section **Konfigurowalne sektory**
- [x] `tests/test_sector_config.py`

## Out of scope

- `orchestrator/` pipeline logic (only type-compatible `JobSector` wrapper)
- LinkedIn scraper implementation
- Scheduler scripts

## Verification

```bash
pytest tests/test_sector_config.py tests/test_false_positive_filter.py tests/test_scrapers.py -q
pytest tests/ -q
python -m job_search.cli list-sectors
python -m job_search.cli run --sector example --profile config/profiles/example_backend.json --max-offers 1 --match-limit 1
```

## Adding a custom sector

1. Copy `config/sectors/example.json` → `config/sectors/your_job.json`
2. Edit `id`, `display_name`, `portal_queries`, filter keywords
3. Copy `config/profiles/example_backend.json` → `config/profiles/your_profile.json`
4. Set `target_sectors` to `["your_job"]`
5. Run: `python -m job_search.cli run --sector your_job --profile config/profiles/your_profile.json`

## Migration notes

Existing databases with enum columns require:

```bash
alembic upgrade head
# lub (zalecane na Windows):
python -m job_search.cli migrate
```

Fresh installs via `init-db` create `String(64)` columns directly. Existing `data` / `automation` row values remain valid.
