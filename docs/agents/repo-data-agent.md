# Task: Repo / Data Agent — Integracja i Pamięć

**Branch:** `feature/memory-integration`  
**Moduły:** `src/job_search/memory/`, `scripts/`, `migrations/`, `tests/`  
**Priorytet:** P0 (blokuje pozostałych agentów)

---

## Cel

Dostarczyć w pełni działającą warstwę pamięci (SQLite/PostgreSQL + ChromaDB) z deduplikacją ofert i gwarancją braku powtórnych rekomendacji.

---

## Zakres prac

### 1. Inicjalizacja bazy relacyjnej

- [ ] Zweryfikować modele ORM w `memory/models.py` (już zdefiniowane).
- [ ] Upewnić się, że `scripts/init_db.py` tworzy katalog `data/` i wszystkie tabele.
- [ ] Dodać test integracyjny: `upsert` tej samej oferty dwa razy → `is_new=False`, aktualizacja `last_seen_at`.
- [ ] Dodać test: `was_already_recommended()` zwraca `True` po zapisie w `recommendations`.

### 2. Repozytoria

- [ ] Rozszerzyć `JobOfferRepository`:
  - `get_unmatched_offers(candidate_name, sector)` — oferty bez wpisu w `match_results`.
  - `mark_recommended(job_offer_id, candidate_name, channel)`.
  - `deactivate_stale_offers(source, older_than_days=30)`.
- [ ] Dodać `UserPreferenceRepository` z metodami `save_profile()` / `load_profile()`.

### 3. ChromaDB (Vector Memory)

- [ ] Zaimplementować helper `build_offer_document(offer: JobOfferCreate) -> str` (tytuł + opis + skills).
- [ ] Zaimplementować `EmbeddingService` w nowym pliku `memory/embeddings.py`:
  - metoda `embed_text(text: str) -> list[float]` via OpenAI API.
  - cache embeddingów w SQLite (opcjonalna tabela `embedding_cache`).
- [ ] Po `upsert` oferty — automatyczny `VectorMemory.upsert_job_offer()`.
- [ ] Test: query podobnych ofert po embeddingu profilu zwraca sensowne wyniki.

### 4. Migracje Alembic

- [ ] Skonfigurować `alembic.ini` w root projektu.
- [ ] Wygenerować migrację początkową z `001_initial_schema.py` (obecnie stub).

### 5. Konfiguracja PostgreSQL (prod)

- [ ] Udokumentować w README sekcję „Production setup” z `DATABASE_URL=postgresql+psycopg2://...`.
- [ ] Test połączenia z PostgreSQL via Docker Compose (opcjonalny `docker-compose.yml`).

---

## Definition of Done

- `python scripts/init_db.py` działa bez błędów.
- `pytest tests/` — wszystkie testy memory przechodzą.
- Brak możliwości zapisania duplikatu `(source, external_id)`.
- Oferta raz polecona nie pojawia się ponownie w wynikach.

---

## Pliki do edycji

```
src/job_search/memory/embeddings.py   (NOWY)
src/job_search/memory/repositories.py
src/job_search/memory/vector_store.py
scripts/init_db.py
tests/test_memory_integration.py      (NOWY)
migrations/
alembic.ini                           (NOWY)
```

---

## Zależności od innych agentów

- **Dostarczasz interfejs** dla Scraper Agent: `JobOfferRepository.upsert()`.
- **Dostarczasz interfejs** dla Matching Agent: `VectorMemory.query_similar_offers()`, `MatchResultRepository.save_result()`.

---

## Przykładowe polecenie testowe

```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/init_db.py
pytest tests/test_repositories.py tests/test_memory_integration.py -v
```
