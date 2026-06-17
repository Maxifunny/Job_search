# AGENTS.md

## Cursor Cloud specific instructions

Single Python 3.11+ product ("Job Search"): a CLI + Streamlit UI that scrapes job
portals into SQLite + ChromaDB and matches offers with an LLM. Standard commands
live in `README.md`; only the non-obvious cloud caveats are captured here.

### Environment
- Dependencies are installed into the **system `python3`** (3.12, user site
  `~/.local`) by the startup update script — no virtualenv. `python3 -m streamlit`,
  `python3 -m pytest`, and `python3 -m job_search.cli` work out of the box from
  `/workspace`; no activation step is needed.
- There is no lockfile; `requirements.txt` + editable install (`pip install -e .`)
  is the source of truth. `ruff` is installed separately (it is configured in
  `pyproject.toml` but intentionally not in `requirements.txt`).
- Console scripts (`streamlit`, `ruff`, `job-search`) land in `~/.local/bin`, which is
  on PATH in normal login shells. If a script is "not found" in a stripped-down shell,
  use the `python3 -m <tool>` form (or add `~/.local/bin` to PATH).

### Running commands (non-obvious)
- The CLI imports both `config` (repo root) and `job_search` (under `src/`). It only
  works after `pip install -e .` (registers `job_search`) AND when invoked from the
  repo root (so `config` resolves). Run `python3 -m job_search.cli <cmd>` from `/workspace`.
- `python3 -m job_search.cli init-db` does NOT create the `data/` directory and fails
  with `unable to open database file` if it is missing. Either run `python3 scripts/init_db.py`
  (which creates `data/`) or `mkdir -p data` first. `data/` is gitignored.
- `alembic upgrade head` / `python3 -m job_search.cli migrate` must be run from the
  repo root (that is where `alembic.ini` lives).
- First setup: `mkdir -p data && python3 -m job_search.cli init-db && python3 -m job_search.cli migrate`.

### Lint / test / build
- Tests: `pytest tests/ -q` (71 tests). The suite mocks embeddings and uses in-memory
  SQLite, so it needs no DB, network, or `LLM_API_KEY`.
- Lint: `ruff check .` runs but currently reports ~39 pre-existing style issues in the
  repo; these are not environment problems.

### Services
- CLI pipeline (`scrape` / `match` / `run`) is the core product. `scrape` hits real
  portals and can take ~2+ minutes per source due to `SCRAPER_REQUEST_DELAY_SECONDS=2`
  rate limiting across multiple queries/pages. LinkedIn may return 403/429 from server IPs.
- Streamlit UI: `python3 -m streamlit run ui/app.py --server.headless true --server.port 8501`
  (or `./scripts/run_ui.sh`). It reads the same SQLite DB and visualizes scraped offers.
- `LLM_API_KEY` (OpenAI-compatible, in `.env`) is required ONLY for `match`, `run`, and
  `scrape --sync-vectors` (embeddings/LLM evaluation). Plain `scrape` and the test suite
  do not need it. `.env` is gitignored; copy `.env.example` (or `.env.gemini.example`).
