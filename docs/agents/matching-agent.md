# Task: Matching Agent — AI Logic

**Branch:** `feature/matching-llm`  
**Moduły:** `src/job_search/matching/`  
**Priorytet:** P1 (równolegle ze scraperem, po gotowości VectorMemory)

---

## Cel

Inteligentne dopasowywanie ofert do profilu kandydata z eliminacją fałszywie pozytywnych wyników (np. „Data Entry” ≠ „Data Scientist”) przy użyciu embeddingów i LLM.

---

## Architektura matchingu

```
Oferta + Profil
      │
      ▼
[FalsePositiveFilter] ──reject──► zapis MatchResult(REJECTED)
      │ pass
      ▼
[Already recommended?] ──skip──► MatchResult(SKIPPED)
      │ no
      ▼
[SemanticMatcher.score()] ──< threshold──► REJECTED
      │ pass
      ▼
[LLMEvaluator.evaluate()] ──< confidence──► REJECTED
      │ pass
      ▼
MatchResult(ACCEPTED) → Recommendation
```

---

## Zakres prac

### 1. SemanticMatcher (`matching/semantic_matcher.py`)

- [ ] Zbudować tekst profilu: umiejętności + CV + target_roles.
- [ ] Zbudować tekst oferty: tytuł + description + requirements + skills.
- [ ] Obliczyć embeddingi via `EmbeddingService` (z memory module).
- [ ] Cosine similarity → score [0, 1].
- [ ] Alternatywnie: query ChromaDB `query_similar_offers()` i normalizacja dystansu.
- [ ] Test: profil „Python, SQL, pandas” vs oferta Data Engineer → score > 0.7.
- [ ] Test: profil Data Scientist vs oferta „Data Entry” → score < 0.5.

### 2. LLMEvaluator (`matching/llm_evaluator.py`)

- [ ] Prompt systemowy (PL lub EN) oceniający:
  - Czy tytuł/rola jest relewantna dla sektora?
  - Które umiejętności kandydata pokrywają wymagania?
  - Czy to fałszywie pozytywne dopasowanie słów kluczowych?
- [ ] Structured output (JSON):
  ```json
  {
    "score": 0.85,
    "confidence": 0.92,
    "is_relevant_role": true,
    "matched_skills": ["Python", "SQL"],
    "missing_skills": ["Spark"],
    "explanation": "..."
  }
  ```
- [ ] Użyj `openai` SDK z `response_format={"type": "json_object"}`.
- [ ] Obsługa braku `LLM_API_KEY` — graceful skip z logiem (dev mode).

### 3. Rozszerzenie FalsePositiveFilter

- [ ] Reguły sektorowe:
  - Data: odrzuć jeśli tytuł zawiera „entry”, „wprowadzanie”, „administrator danych” bez analitycznych skilli.
  - Automation: odrzuć „operator produkcji”, „monter” bez PLC/SCADA w opisie.
- [ ] Konfigurowalna lista `excluded_keywords` z `CandidateProfile`.
- [ ] Testy parametryzowane (pytest `@pytest.mark.parametrize`).

### 4. Integracja z MatchingEngine

- [ ] Po `evaluate_offer()` — zapis wyniku via `MatchResultRepository.save_result()`.
- [ ] Przy `ACCEPTED` — `JobOfferRepository.mark_recommended()`.
- [ ] CLI: `python -m job_search.cli match --profile config/profiles/default.json`.

### 5. Profile kandydata

Nowy plik: `config/profiles/default.json`

```json
{
  "name": "default",
  "target_sectors": ["data", "automation"],
  "target_roles": ["Data Engineer", "Programista PLC"],
  "skills": [
    {"name": "Python", "years": 3},
    {"name": "SQL", "years": 4},
    {"name": "TIA Portal", "years": 2}
  ],
  "excluded_keywords": ["data entry", "staż bez wynagrodzenia"],
  "cv_text": "..."
}
```

---

## Przykładowy prompt LLM (szkic)

```
Jesteś ekspertem HR w branży IT i automatyki przemysłowej.
Oceń dopasowanie kandydata do oferty pracy.

KANDYDAT:
- Docelowe role: {target_roles}
- Umiejętności: {skills}
- CV: {cv_text}

OFERTA:
- Tytuł: {title}
- Firma: {company}
- Opis: {description}
- Wymagania: {requirements}

Odpowiedz w JSON. Odrzuć oferty gdzie tytuł sugeruje inną rolę
(np. "Data Entry" dla profilu "Data Scientist").
```

---

## Definition of Done

- `SemanticMatcher.score()` działa z mock embeddingami.
- `LLMEvaluator.evaluate()` zwraca sparsowany `LLMEvaluation`.
- Pipeline: oferta „Data Entry” → `REJECTED` z powodem.
- Pipeline: oferta „Data Engineer (Python, SQL)” → `ACCEPTED`.
- Wyniki persystowane w `match_results` — ta sama para (offer, candidate) nie jest oceniana ponownie (cache).

---

## Pliki do edycji / utworzenia

```
src/job_search/matching/semantic_matcher.py
src/job_search/matching/llm_evaluator.py
src/job_search/matching/filters.py
src/job_search/matching/engine.py
src/job_search/matching/prompts.py          (NOWY)
config/profiles/default.json              (NOWY)
tests/test_semantic_matcher.py              (NOWY)
tests/test_llm_evaluator.py               (NOWY)
tests/test_false_positive_filter.py         (NOWY)
```

---

## Progi konfiguracyjne (`.env`)

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `MIN_SEMANTIC_SCORE` | 0.65 | Min. cosine similarity |
| `MIN_LLM_CONFIDENCE` | 0.70 | Min. pewność LLM |

---

## Zależności

- **Wymaga:** `EmbeddingService` z Repo/Data Agent.
- **Wymaga:** `JobOfferCreate`, `CandidateProfile` ze `schemas/`.
- **Dostarcza:** `MatchingEngine` dla Master Agent pipeline.

---

## Testy

```bash
pytest tests/test_false_positive_filter.py tests/test_semantic_matcher.py -v
# Testy LLM z mock openai:
pytest tests/test_llm_evaluator.py -v
```
