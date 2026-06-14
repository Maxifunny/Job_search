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
│       └── matching-agent.md
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
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .                   # wymagane — rejestruje moduły config i job_search
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
# lub (po pip install -e .):
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
| Master Agent | `orchestrator/` | Integracja pipeline (Krok 2) |

### Konwencje Git

```
feature/memory-*     → Repo/Data Agent
feature/scraper-*    → Scraper Agent
feature/matching-*   → Matching Agent
feature/pipeline-*   → Master Agent
```

Każdy agent pracuje na własnym branchu i otwiera Pull Request do `main`.

## CLI (planowane komendy)

```bash
python -m job_search.cli init-db
python -m job_search.cli scrape --source justjoin --sector data
python -m job_search.cli match --profile config/profiles/default.json
python -m job_search.cli run --sector automation
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
| Memory (implementacja) | 🔲 Krok 2 — Repo/Data Agent |
| Scrapers | 🔲 Krok 2 — Scraper Agent |
| Matching (LLM) | 🔲 Krok 2 — Matching Agent |
| Pipeline orchestrator | 🔲 Krok 3 — Master Agent |

## Licencja

Projekt prywatny — repozytorium [Maxifunny/Job_search](https://github.com/Maxifunny/Job_search).
