"""HTML parsing helpers for job portal scrapers."""

from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup

OFFER_ID_RE = re.compile(r",oferta,(\d+)")
WHITESPACE_RE = re.compile(r"\s+")


def html_to_text(html: str | None) -> str:
    """Convert HTML fragment to plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    return WHITESPACE_RE.sub(" ", unescape(text)).strip()


def extract_pracuj_offer_id(url: str) -> str | None:
    match = OFFER_ID_RE.search(url)
    return match.group(1) if match else None


def extract_pracuj_offer_links(html: str, base_url: str = "https://www.pracuj.pl") -> list[str]:
    """Extract unique offer URLs from a Pracuj.pl search results page."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href*=',oferta,']"):
        href = anchor.get("href")
        if not href:
            continue
        if href.startswith("/"):
            href = f"{base_url}{href}"
        if ",oferta," not in href:
            continue
        clean = href.split("?")[0]
        if clean not in seen:
            seen.add(clean)
            links.append(clean)

    return links


def parse_pracuj_offer_page(html: str, url: str) -> dict[str, object]:
    """Parse a Pracuj.pl offer detail page into normalized fields."""
    soup = BeautifulSoup(html, "lxml")
    offer_id = extract_pracuj_offer_id(url)
    if offer_id is None:
        raise ValueError(f"Could not extract offer id from URL: {url}")

    title_node = soup.select_one('[data-test="text-offer-title"]') or soup.find("h1")
    title = title_node.get_text(strip=True) if title_node else "Unknown title"

    company_node = (
        soup.select_one('[data-test="text-company-name"]')
        or soup.select_one('[data-test="offer-company-name"]')
        or soup.select_one("h2")
    )
    company = company_node.get_text(strip=True) if company_node else "Unknown company"

    location_node = soup.select_one('[data-test="text-workplace-address"]')
    location = location_node.get_text(strip=True) if location_node else None

    sections: list[str] = []
    for heading in soup.select("h2, h3"):
        heading_text = heading.get_text(strip=True)
        if not heading_text:
            continue
        sibling_texts: list[str] = []
        for sibling in heading.find_next_siblings():
            if sibling.name in {"h1", "h2", "h3"}:
                break
            text = sibling.get_text("\n", strip=True)
            if text:
                sibling_texts.append(text)
        if sibling_texts:
            sections.append(f"{heading_text}\n" + "\n".join(sibling_texts))

    description = "\n\n".join(sections) if sections else html_to_text(html)
    requirements = ""
    for section in sections:
        lowered = section.lower()
        if "wymagania" in lowered or "requirements" in lowered:
            requirements = section
            break

    skills: list[str] = []
    for node in soup.select('[data-test="technologies-section"] li, .tag, .tags li'):
        skill = node.get_text(strip=True)
        if skill and skill not in skills:
            skills.append(skill)

    remote = any(
        token in html.lower()
        for token in ("praca zdalna", "praca hybrydowa", "praca mobilna", "remote")
    )

    salary_min, salary_max = _parse_salary_from_text(html)

    return {
        "external_id": offer_id,
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "requirements": requirements or None,
        "skills": skills,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "remote": remote,
        "url": url,
    }


def _parse_salary_from_text(text: str) -> tuple[float | None, float | None]:
    match = re.search(
        r"(\d[\d\s]{2,})\s*[–-]\s*(\d[\d\s]{2,})\s*zł",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None
    low = float(match.group(1).replace(" ", ""))
    high = float(match.group(2).replace(" ", ""))
    return low, high
