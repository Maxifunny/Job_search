# Job Search — Autonomiczny System Wyszukiwania i Dopasowywania Ofert

Inteligentny system do wyszukiwania, analizy i precyzyjnego dopasowywania ofert pracy w sektorach **Data** (Analyst, Engineer, Scientist) oraz **Automatyka** (Automatyk, Programista PLC, Automation Engineer).

## Kluczowe cechy

- **Pamięć krótko- i długoterminowa** — SQLite/PostgreSQL + ChromaDB
- **Brak powtórnych rekomendacji** — deduplikacja via `(source, external_id)` i tabela `recommendations`
- **Inteligentny matching** — embeddingi semantyczne + ocena LLM (nie tylko słowa kluczowe)
- **Modułowa architektura** — niezależna praca subagentów na osobnych branchach

## Stack technologiczny

| Komponent | Technologia |
|-----------|-------------|
| Język | Python 3.11+ |
| ORM | SQLAlchemy 2 |
| Baza relacyjna | SQLite (dev) / PostgreSQL (prod) |
| Baza wektorowa | ChromaDB |
| LLM | OpenAI-compatible API |
| Scraping | httpx, BeautifulSoup, Selenium |
| Testy | pytest |

## Struktura projektu

```
Job_search/
├── config/                     # Ustawienia (pydantic-settings)
├── docs/
│   ├── architecture.md         # Pełna architektura + diagramy
│   └── agents/                 # Taski dla subagentów
│       ├── repo-data-agent.md
│       ├── scraper-agent.md
│       ├── matching-agent.md
│       └── profile-agent.md
├── migrations/                 # Alembic
├── scripts/init_db.py          # Bootstrap bazy
├── src/job_search/
│   ├── memory/                 # Pamięć (Repo/Data Agent)
│   ├── scrapers/               # Scrapery portali (Scraper Agent)
│   ├── matching/               # LLM + semantic matching (Matching Agent)
│   ├── orchestrator/           # Pipeline (Master Agent)
│   └── schemas/                # Wspólne modele danych
└── tests/
```

## Szybki start

### 1. Instalacja

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfiguracja

```bash
# Domyślna (OpenAI) lub Gemini (Google AI Studio, free tier):
cp .env.example .env
# cp .env.gemini.example .env

# Gemini: klucz z https://aistudio.google.com/apikey → LLM_API_KEY w .env
```

### 3. Inicjalizacja bazy danych

```bash
python scripts/init_db.py
# lub
python -m job_search.cli init-db
```

### 4. Testy

```bash
pytest tests/ -v
```

## Schemat bazy danych (Memory)

### Tabele relacyjne

| Tabela | Opis |
|--------|------|
| `job_offers` | Kanoniczny rejestr ofert. Unikalność: `(source, external_id)` |
| `match_results` | Wyniki oceny semantic + LLM per kandydat |
| `recommendations` | Oferty już polecone — zapobiega duplikatom |
| `scrape_runs` | Audyt uruchomień scraperów |
| `user_preferences` | Profil kandydata (JSON) |

### Kolekcje ChromaDB

| Kolekcja | Zawartość |
|----------|-----------|
| `job_offers` | Embeddingi opisów ofert |
| `user_preferences` | Embeddingi profilu/CV kandydata |

Szczegóły: [docs/architecture.md](docs/architecture.md)

## Przepływ systemu

```
Portale pracy → Scrapers → Memory (SQL + Chroma)
                                ↓
Profil kandydata → Matching (filter → semantic → LLM)
                                ↓
                         Rekomendacje (bez duplikatów)
```

## Zespół subagentów

| Agent | Moduł | Task |
|-------|-------|------|
| Repo/Data Agent | `memory/` | [docs/agents/repo-data-agent.md](docs/agents/repo-data-agent.md) |
| Scraper Agent | `scrapers/` | [docs/agents/scraper-agent.md](docs/agents/scraper-agent.md) |
| Matching Agent | `matching/` | [docs/agents/matching-agent.md](docs/agents/matching-agent.md) |
| Master Agent | `orchestrator/` | [docs/agents/pipeline-agent.md](docs/agents/pipeline-agent.md) |

### Konwencje Git

```
feature/memory-*     → Repo/Data Agent
feature/scraper-*    → Scraper Agent
feature/matching-*   → Matching Agent
feature/pipeline-*   → Master Agent
```

Każdy agent pracuje na własnym branchu i otwiera Pull Request do `main`.

## CLI

```bash
python -m job_search.cli init-db
python -m job_search.cli scrape --sector data
python -m job_search.cli scrape --sector data --source justjoin
python -m job_search.cli scrape --sector automation --source pracuj_pl
python -m job_search.cli scrape --sector data --sync-vectors
python -m job_search.cli match --profile config/profiles/default.json
```

Portale: `justjoin`, `pracuj_pl`, `nofluffjobs` (domyślnie wszystkie naraz).

```bash
python -m job_search.cli list-sectors
```

## Konfigurowalne sektory

Sektory pracy są definiowane w plikach JSON w `config/sectors/`. Możesz dodać własny zawód bez zmian w kodzie — wystarczy nowy plik sektora i profil kandydata.

### Wbudowane sektory

| Id | Opis |
|----|------|
| `data` | Data Analyst, Engineer, Scientist |
| `automation` | Automatyk, PLC, SCADA |
| `example` | Szablon Backend Developer (do kopiowania) |

### Lista dostępnych sektorów

```bash
python -m job_search.cli list-sectors
```

### Dodanie własnego sektora

1. Skopiuj szablon: `config/sectors/example.json` → `config/sectors/twoj_zawod.json`
2. Uzupełnij `id`, `display_name`, `portal_queries`, słowa kluczowe filtrów
3. Skopiuj profil: `config/profiles/example_backend.json` → `config/profiles/twoj_profil.json`
4. Ustaw `"target_sectors": ["twoj_zawod"]` w profilu

### Przykłady (PowerShell)

```powershell
# Lista sektorów
python -m job_search.cli list-sectors

# Scrapowanie własnego sektora
python -m job_search.cli scrape --sector example

# Pełny pipeline z własnym profilem
python -m job_search.cli run --sector example --profile config/profiles/example_backend.json

# Własny sektor + własny profil (po dodaniu plików JSON)
python -m job_search.cli run --sector twoj_zawod --profile config/profiles/twoj_profil.json
```

Struktura pliku sektora (`config/sectors/example.json`):

```json
{
  "id": "example",
  "display_name": "Backend Developer (example template)",
  "portal_queries": {
    "justjoin": ["python", "backend"],
    "pracuj_pl": ["backend developer", "python developer"],
    "nofluffjobs": ["backend", "python"],
    "linkedin": []
  },
  "false_positive_title_keywords": ["frontend", "graphic designer"],
  "required_skill_keywords": ["python", "django", "fastapi", "backend", "api"]
}
```

### Pełny pipeline — `run`

Jedna komenda uruchamia cały przepływ **SCRAPE → STORE → MATCH → RECOMMEND**:

```bash
# Pełny pipeline — sektor Data
python -m job_search.cli run --sector data --profile config/profiles/default.json

# Szybki test (5 ofert na portal, 5 ocen LLM — oszczędność API)
python -m job_search.cli run --sector data --max-offers 5 --match-limit 5

# Tylko JustJoin, sektor Automatyka
python -m job_search.cli run --sector automation --source justjoin

# Windows Task Scheduler — codziennie o 8:00
# Program: python   Args: -m job_search.cli run --sector data --max-offers 30 --match-limit 20
```

| Argument | Opis |
|----------|------|
| `--sector SECTOR` | wymagany — slug z `list-sectors` (np. `data`, `example`) |
| `--profile PATH` | domyślnie `config/profiles/default.json` |
| `--source {justjoin,pracuj_pl,nofluffjobs}` | opcjonalny (domyślnie wszystkie portale) |
| `--max-offers INT` | limit scrapowania per portal |
| `--max-pages INT` | limit stron per portal |
| `--match-limit INT` | limit ofert do oceny LLM (oszczędność API) |
| `--no-sync-vectors` | pomiń ChromaDB przy scrape (tylko debug) |

Przykładowy output:

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

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `DATABASE_URL` | `sqlite:///./data/job_search.db` | Połączenie SQL |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Katalog ChromaDB |
| `LLM_API_KEY` | — | Klucz API LLM |
| `LLM_MODEL` | `gpt-4o-mini` | Model do oceny dopasowania |
| `MIN_SEMANTIC_SCORE` | `0.65` | Próg podobieństwa semantycznego |
| `MIN_LLM_CONFIDENCE` | `0.70` | Próg pewności LLM |

Pełna lista: [.env.example](.env.example) · Gemini: [.env.gemini.example](.env.gemini.example)

## Status projektu

| Moduł | Status |
|-------|--------|
| Architektura + schemat DB | ✅ Krok 1 |
| Memory (implementacja) | ✅ Repo/Data Agent |
| Scrapers | ✅ Scraper Agent |
| Matching (LLM) | ✅ Matching Agent |
| Pipeline orchestrator | ✅ Master Agent (komenda `run`) |

## Licencja

Projekt prywatny — repozytorium [Maxifunny/Job_search](https://github.com/Maxifunny/Job_search).
