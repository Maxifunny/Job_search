# Task: LinkedIn Scraper Agent

**Branch:** `cursor/linkedin-scraper-503f`  
**Base branch:** `cursor/profile-config-503f`  
**Module:** `src/job_search/scrapers/sources/linkedin.py`

---

## Goal

Implement LinkedIn job scraping via the **guest jobs API** (no login) and register the scraper so CLI works:

```bash
python -m job_search.cli scrape --source linkedin --sector data --max-offers 5
```

---

## API

| Item | Value |
|------|-------|
| Endpoint | `LINKEDIN_GUEST_API_BASE` (default: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`) |
| Params | `keywords`, `location` (`LINKEDIN_JOBS_LOCATION`, default `Poland`), `start` (pagination, step 25) |
| Response | HTML fragments with `div.base-card` job cards |

### Parsed fields

- `external_id` — numeric LinkedIn job ID
- `title`, `company`, `location` — from card headings
- `url` — `https://www.linkedin.com/jobs/view/{id}`
- `description` — card snippet (no extra detail fetch by default)

---

## Sector queries

Read `portal_queries.linkedin` from `config/sectors/*.json` via `queries_for_sector(sector_id, "linkedin")`.

Fallback when empty:

1. First query from another portal in the same sector config
2. Sector `display_name` (text before `(`)

---

## Error handling

| Condition | Behavior |
|-----------|----------|
| HTTP 403 / 429 | Append to `ScraperResult.errors`, return partial/empty offers |
| No queries | Skip with clear error message |
| `health_check()` | GET guest search with `keywords=test&location=Poland&start=0` |

---

## Limitations

- **Guest API only** — no authenticated LinkedIn session or cookie-based scraping
- **Rate limits** — LinkedIn may block datacenter IPs (403/429); residential IP may be required
- **Minimal descriptions** — uses search-card snippet, not full job posting HTML
- **No salary/skills** — not available on guest search cards

---

## Tests

```bash
pytest tests/test_linkedin_scraper.py -v
```

Uses `tests/fixtures/linkedin_search.html` — no live LinkedIn calls in CI.

---

## Files touched

- `src/job_search/scrapers/sources/linkedin.py`
- `src/job_search/scrapers/registry.py`
- `config/settings.py` — `linkedin_jobs_location`, `linkedin_guest_api_base`
- `config/sectors/{data,automation,example}.json` — `portal_queries.linkedin`
- `.env.example`
- `tests/fixtures/linkedin_search.html`
- `tests/test_linkedin_scraper.py`
- `README.md`
