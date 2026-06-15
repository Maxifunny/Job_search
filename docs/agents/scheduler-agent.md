# Scheduler Agent — Windows Task Scheduler

**Branch:** `cursor/scheduler-windows-503f`  
**Pliki:** `scripts/windows/*.ps1`, `docs/agents/scheduler-agent.md`, `README.md`

---

## Cel

Umożliwić użytkownikowi Windows codzienne (lub według harmonogramu) uruchamianie pipeline’u job search bez ręcznego wpisywania komend — przez **Harmonogram zadań Windows** (Task Scheduler).

---

## Definition of Done

- [x] `scripts/windows/run_job_search.ps1` — wrapper z logowaniem, venv, parametrami CLI
- [x] `scripts/windows/register_scheduled_task.ps1` — rejestracja / `-Unregister` zadania `JobSearch-Daily`
- [x] `docs/agents/scheduler-agent.md` — instalacja, odinstalowanie, troubleshooting
- [x] `README.md` — sekcja **Windows Task Scheduler** z przykładem PowerShell
- [x] `.gitignore` — katalog `logs/` (już obecny)
- [x] (opcjonalnie) `python -m job_search.cli schedule` — wypisuje komendy rejestracji

## Out of scope

- Pythonowy scheduler / cron (APScheduler, celery beat)
- Zmiany w `scrapers/`, `matching/`, `memory/`, `orchestrator/`
- Testy Pester (skrypty PS1 weryfikowane ręcznie na Windows)

---

## Instalacja (Windows)

### Wymagania wstępne

1. Python 3.11+ z venv w katalogu repozytorium (`.venv`)
2. Plik `.env` z `LLM_API_KEY` (i opcjonalnie `DATABASE_URL`)
3. Zainicjalizowana baza: `python -m job_search.cli init-db`

### 1. Jednorazowy test ręczny

```powershell
cd C:\ścieżka\do\Job_search
.\scripts\windows\run_job_search.ps1 -Sector data -Profile config\profiles\default.json
```

Log: `logs\job_search_YYYYMMDD_HHmmss.log`

### 2. Rejestracja zadania (Administrator)

Otwórz **PowerShell jako administrator**:

```powershell
cd C:\ścieżka\do\Job_search
.\scripts\windows\register_scheduled_task.ps1 -Sector data -Profile config\profiles\default.json
```

Domyślnie: codziennie o **08:00**, zadanie `JobSearch-Daily`, źródło `justjoin`, `--max-offers 30`, `--match-limit 20`, `--no-sync-vectors`.

Parametry opcjonalne:

| Parametr | Domyślnie | Opis |
|----------|-----------|------|
| `-TaskName` | `JobSearch-Daily` | Nazwa w Harmonogramie zadań |
| `-Hour` / `-Minute` | `8` / `0` | Godzina uruchomienia |
| `-Source` | `justjoin` | Portal (`justjoin`, `pracuj_pl`, `nofluffjobs`) |
| `-MaxOffers` | `30` | Limit ofert per portal |
| `-MatchLimit` | `20` | Limit ocen LLM |
| `-SyncVectors` | wyłączone | Włącz embeddingi ChromaDB |
| `-RunAsUser` | — | Uruchom tylko gdy użytkownik zalogowany (sesja interaktywna) |

### 3. Weryfikacja

- `taskschd.msc` → **Biblioteka harmonogramu zadań** → `JobSearch-Daily`
- Prawy przycisk → **Uruchom** — sprawdź log w `logs\`

---

## Odinstalowanie

```powershell
.\scripts\windows\register_scheduled_task.ps1 -Unregister
# lub z własną nazwą:
.\scripts\windows\register_scheduled_task.ps1 -Unregister -TaskName JobSearch-Daily
```

---

## Troubleshooting

### Brak `.venv` / błąd aktywacji

Skrypt `run_job_search.ps1` kończy się komunikatem po polsku. Utwórz venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Upewnij się, że w Harmonogramie zadań **Katalog startowy** wskazuje na root repozytorium (ustawiane automatycznie przez `register_scheduled_task.ps1`).

### Brak `LLM_API_KEY` w `.env`

Pipeline dopasowania wymaga klucza API. Skopiuj `.env.example` → `.env` i uzupełnij `LLM_API_KEY`. Plik `.env` musi leżeć w katalogu głównym repozytorium — `config/settings.py` ładuje go przy starcie Pythona.

Zadanie harmonogramu uruchamia się bez interaktywnej sesji — zmienne środowiskowe systemowe **nie zastępują** `.env` w repozytorium.

### Pracuj.pl — błąd 403

Portal może blokować żądania bez odpowiednich nagłówków lub przy zbyt częstym scrapingu. Na start użyj `-Source justjoin` (domyślne w skryptach). Pełna lista portali: `python -m job_search.cli scrape --help`.

### ChromaDB / embeddingi

Domyślnie skrypt używa `--no-sync-vectors` (szybszy run, mniej zależności od API). Aby włączyć wektory przy harmonogramie:

```powershell
.\scripts\windows\register_scheduled_task.ps1 -Sector data -SyncVectors
```

Reset Chroma (dev): usuń katalog `./data/chroma` lub ustaw `CHROMA_PERSIST_DIR` w `.env`, potem ponownie `scrape --sync-vectors`.

### Zadanie nie startuje / kod wyjścia ≠ 0

1. Otwórz najnowszy plik w `logs\`
2. Uruchom ręcznie tę samą komendę co w logu
3. Sprawdź uprawnienia użytkownika zadania w `taskschd.msc`
4. Przy `-RunAsUser` — użytkownik musi być zalogowany

### Rejestracja — „wymaga Administratora”

Tylko **rejestracja** i **aktualizacja** zadania wymagają PowerShell jako Administrator. Samo `run_job_search.ps1` i `-Unregister` można uruchomić zwykłym użytkownikiem (usunięcie może wymagać uprawnień do zadania).

---

## CLI helper

```bash
python -m job_search.cli schedule --sector data --profile config/profiles/default.json
```

Wypisuje gotowe komendy PowerShell do skopiowania (bez wywołań Windows API z Pythona).

---

## Weryfikacja (dev / CI)

```bash
test -f scripts/windows/run_job_search.ps1
test -f scripts/windows/register_scheduled_task.ps1
test -f docs/agents/scheduler-agent.md
grep -q "Windows Task Scheduler" README.md
python -m job_search.cli schedule --help
```
