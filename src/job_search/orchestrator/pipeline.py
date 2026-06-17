"""High-level pipeline: scrape → store → match → recommend."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import get_settings
from job_search.matching.service import match_pending_offers
from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobSector
from job_search.scrapers.service import scrape_and_persist


@dataclass
class PipelineResult:
    """Aggregated outcome of a full scrape → store → match → report run."""

    sector: JobSector
    scraped: int = 0
    new_offers: int = 0
    updated_offers: int = 0
    evaluated: int = 0
    accepted: int = 0
    rejected: int = 0
    skipped: int = 0
    recommendations: list[str] = field(default_factory=list)
    scrape_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class JobSearchPipeline:
    """
    Master orchestrator coordinating scrapers, memory, and matching.

    Reuses the existing ``scrape_and_persist`` (scrapers) and
    ``match_pending_offers`` (matching) services — it only coordinates the flow
    and aggregates a :class:`PipelineResult`; it does not implement scraping or
    LLM logic itself.
    """

    def run(
        self,
        sector: JobSector,
        profile: CandidateProfile,
        *,
        source: str | None = None,
        sync_vectors: bool = True,
        max_offers: int | None = None,
        max_pages: int | None = None,
        match_limit: int | None = None,
        db_only: bool = False,
    ) -> PipelineResult:
        result = PipelineResult(sector=sector)

        if not get_settings().llm_api_key:
            print(
                "[pipeline] Ostrzeżenie: brak LLM_API_KEY — matching działa w trybie dev."
            )

        # --- Krok 1+2: Scrape + Store -------------------------------------
        if db_only:
            print("[pipeline] Krok 1/3: Pomijam scrapowanie (--db-only).")
            scrape_summaries = []
        else:
            print("[pipeline] Krok 1/3: Scrapowanie ofert...")
            scrape_kwargs: dict[str, int] = {}
            if max_offers is not None:
                scrape_kwargs["max_offers"] = max_offers
            if max_pages is not None:
                scrape_kwargs["max_pages"] = max_pages

            try:
                scrape_summaries = scrape_and_persist(
                    sector,
                    source=source,
                    sync_vectors=sync_vectors,
                    **scrape_kwargs,
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                message = f"Scrape failed: {exc}"
                print(f"[pipeline] {message}")
                result.scrape_errors.append(message)
                scrape_summaries = []

        for summary in scrape_summaries:
            result.scraped += summary.offers_found
            result.new_offers += summary.offers_new
            result.updated_offers += summary.offers_updated
            result.scrape_errors.extend(summary.errors)
            print(
                f"[{summary.source}] found={summary.offers_found} "
                f"new={summary.offers_new} updated={summary.offers_updated}"
            )
            for error in summary.errors:
                print(f"  - {error}")

        if result.scraped == 0:
            print(
                "[pipeline] Brak nowych ofert ze scrapingu — "
                "matching zostanie uruchomiony na ofertach już w bazie."
            )

        # --- Krok 3: Match ------------------------------------------------
        print("[pipeline] Krok 2/3: Dopasowywanie ofert do profilu...")
        try:
            match_summary = match_pending_offers(
                profile,
                sector=sector,
                limit=match_limit,
            )
        except Exception as exc:
            message = f"Matching failed: {exc}"
            print(f"[pipeline] {message}")
            result.errors.append(message)
            print("[pipeline] Krok 3/3: Zakończono z błędami.")
            return result

        result.evaluated = match_summary.evaluated
        result.accepted = match_summary.accepted
        result.rejected = match_summary.rejected
        result.skipped = match_summary.skipped
        for outcome in match_summary.accepted_outcomes:
            offer = outcome.offer
            result.recommendations.append(
                f"{offer.title} @ {offer.company} - {offer.url}"
            )

        print(
            f"[{sector.value}] evaluated={result.evaluated} "
            f"accepted={result.accepted} rejected={result.rejected} "
            f"skipped={result.skipped}"
        )

        # --- Krok 4: Report ----------------------------------------------
        print("[pipeline] Krok 3/3: Gotowe.")
        return result
