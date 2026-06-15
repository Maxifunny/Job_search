"""LLM prompt templates for job-offer evaluation."""

from job_search.schemas.candidate import CandidateProfile
from job_search.schemas.job_offer import JobOfferCreate


def build_evaluation_prompt(offer: JobOfferCreate, profile: CandidateProfile) -> str:
    """Build a Polish evaluation prompt for structured LLM output."""
    target_roles = ", ".join(profile.target_roles) or "brak"
    skills = ", ".join(skill.name for skill in profile.skills) or "brak"
    cv_text = profile.cv_text or "brak"
    requirements = offer.requirements or "brak"
    offer_skills = ", ".join(offer.skills) if offer.skills else "brak"

    return f"""Jesteś ekspertem HR w branży IT i automatyki przemysłowej.
Oceń dopasowanie kandydata do oferty pracy.

KANDYDAT:
- Docelowe role: {target_roles}
- Umiejętności: {skills}
- CV: {cv_text}

OFERTA:
- Tytuł: {offer.title}
- Firma: {offer.company}
- Sektor: {offer.sector}
- Opis: {offer.description}
- Wymagania: {requirements}
- Umiejętności: {offer_skills}

Odpowiedz wyłącznie poprawnym JSON z polami:
- score (float 0-1): ogólne dopasowanie
- confidence (float 0-1): pewność oceny
- is_relevant_role (bool): czy rola jest relewantna dla profilu kandydata
- matched_skills (lista stringów): umiejętności kandydata pokrywające wymagania
- missing_skills (lista stringów): brakujące umiejętności
- explanation (string): krótkie uzasadnienie po polsku

Odrzuć oferty, gdzie tytuł sugeruje inną rolę (np. "Data Entry" dla profilu Data Engineer).
Zwróć JSON bez markdown i bez dodatkowego tekstu."""
