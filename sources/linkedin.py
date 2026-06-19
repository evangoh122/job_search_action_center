"""LinkedIn job source via Apify bebity~linkedin-jobs-scraper actor.

Searches for VP/Head-of data & analytics roles at target banks in Singapore.
HTTP is injectable for offline testing. Runs only when APIFY_TOKEN is set.

ToS note: scraping LinkedIn violates their User Agreement. This is enabled
by the user explicitly setting APIFY_TOKEN — usage is at their own discretion.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx

from models import RawJob
from sources.base import JobSource

logger = logging.getLogger(__name__)

_ACTOR = "bebity~linkedin-jobs-scraper"
_RUN_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"

# LinkedIn location IDs for Singapore
_SG_LOCATION = "Singapore"

HttpPost = Callable[[str, dict], list]


class LinkedInJobSource(JobSource):
    """Pulls Data/AI VP & leadership job listings from LinkedIn via Apify.

    Each search term is queried in sequence; results are deduped by job URL.
    Posted-within filter uses the `postedAt` field from Apify items.
    """

    def __init__(
        self,
        token: str,
        search_terms: list[str],
        location: str = _SG_LOCATION,
        max_age_days: int = 1,
        max_results_per_term: int = 25,
        http_post: HttpPost | None = None,
    ) -> None:
        self.token = token
        self.search_terms = search_terms
        self.location = location
        self.max_age_days = max_age_days
        self.max_results_per_term = max_results_per_term
        self.http_post = http_post or self._default_post

    def _default_post(self, url: str, body: dict) -> list:
        r = httpx.post(url, json=body, timeout=180)  # actor run-sync can be slow
        r.raise_for_status()
        resp = r.json()
        if isinstance(resp, dict):
            return resp.get("items") or resp.get("data") or []
        return resp or []

    @staticmethod
    def _items(resp) -> list:
        if isinstance(resp, dict):
            return resp.get("items") or resp.get("data") or []
        return resp or []

    def _parse_posted_at(self, item: dict) -> datetime | None:
        """Parse `postedAt` from Apify item. Accepts ISO string or epoch ms int."""
        raw = item.get("postedAt") or item.get("postedDate") or ""
        if not raw:
            return None
        try:
            if isinstance(raw, (int, float)):
                return datetime.fromtimestamp(raw / 1000)
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, OSError):
            return None

    def fetch(self) -> list[RawJob]:
        cutoff = datetime.now() - timedelta(days=self.max_age_days)
        seen_urls: set[str] = set()
        results: list[RawJob] = []
        run_url = _RUN_URL.format(actor=_ACTOR, token=self.token)

        for term in self.search_terms:
            payload = {
                "searchKeywords": term,
                "location": self.location,
                "maxResults": self.max_results_per_term,
                "proxy": {"useApifyProxy": True},
            }
            try:
                items = self._items(self.http_post(run_url, payload))
            except Exception:
                logger.warning("LinkedIn fetch failed for term '%s'", term, exc_info=True)
                continue

            for item in items:
                try:
                    job_url = item.get("jobUrl") or item.get("url") or ""
                    if not job_url or job_url in seen_urls:
                        continue

                    company = (item.get("companyName") or "").strip()
                    title = (item.get("title") or item.get("jobTitle") or "").strip()
                    if not company or not title:
                        continue

                    posted_at = self._parse_posted_at(item)
                    if posted_at is not None and posted_at < cutoff:
                        continue

                    description = (item.get("descriptionText") or item.get("description") or "").strip()

                    seen_urls.add(job_url)
                    results.append(RawJob(
                        source="linkedin",
                        company=company,
                        title=title,
                        url=job_url,
                        posted_at=posted_at,
                        ats_type="linkedin",
                        description=description,
                    ))
                except Exception:
                    logger.warning("Skipping malformed LinkedIn item: %s", item, exc_info=True)
                    continue

        logger.info("LinkedIn: fetched %d jobs across %d terms", len(results), len(self.search_terms))
        return results
