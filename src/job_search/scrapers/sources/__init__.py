"""Portal-specific scraper implementations."""

from job_search.scrapers.sources.justjoin import JustJoinScraper
from job_search.scrapers.sources.nofluffjobs import NoFluffJobsScraper
from job_search.scrapers.sources.pracuj_pl import PracujPlScraper

__all__ = ["JustJoinScraper", "NoFluffJobsScraper", "PracujPlScraper"]
