from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx

from models import RawJob
from sources.base import JobSource

logger = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://api.mycareersfuture.gov.sg/v2/search?limit={limit}&page=0"
_DETAIL_URL = "https://api.mycareersfuture.gov.sg/v2/jobs/{uuid}"
_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _default_http_post(url: str, payload: dict) -> dict:
    response = httpx.post(url, json=payload, headers=_DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def _default_http_get(url: str) -> dict:
    response = httpx.get(url, headers=_DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


class MyCareersFutureSource(JobSource):
    """Pulls jobs from the public MyCareersFuture (Singapore) search API.

    `http_post` is injectable so tests never hit the network.
    """

    def __init__(
        self,
        search_terms: list[str],
        max_age_days: int = 1,
        limit: int = 30,
        http_post: Callable[[str, dict], dict] | None = None,
        enrich: bool = True,
        http_get: Callable[[str], dict] | None = None,
    ) -> None:
        self.search_terms = search_terms
        self.max_age_days = max_age_days
        self.limit = limit
        self.http_post = http_post if http_post is not None else _default_http_post
        self.enrich = enrich
        self.http_get = http_get if http_get is not None else _default_http_get

    def _fetch_description(self, uuid: str) -> str:
        """Pull the full job description + skills from the per-job detail endpoint."""
        try:
            d = self.http_get(_DETAIL_URL.format(uuid=uuid))
        except Exception:
            logger.warning("Detail fetch failed for %s", uuid, exc_info=True)
            return ""
        desc = _strip_html(d.get("description", ""))
        skills = " ".join(s.get("skill", "") for s in d.get("skills", []) if s.get("skill"))
        return f"{desc} {skills}".strip()

    def fetch(self) -> list[RawJob]:
        results: dict[str, RawJob] = {}
        cutoff = datetime.now().date() - timedelta(days=self.max_age_days)

        for term in self.search_terms:
            url = _DEFAULT_API_URL.format(limit=self.limit)
            payload = {"search": term, "sortBy": ["new_posting_date"]}

            try:
                data = self.http_post(url, payload)
            except Exception:
                logger.warning("Failed to fetch search term: %s", term, exc_info=True)
                continue

            for item in data.get("results", []):
                try:
                    job_uuid = item["uuid"]
                    if job_uuid in results:
                        continue

                    posted_at = datetime.fromisoformat(item["metadata"]["newPostingDate"])
                    if posted_at.date() < cutoff:
                        continue

                    description = self._fetch_description(job_uuid) if self.enrich else ""
                    results[job_uuid] = RawJob(
                        source="mycareersfuture",
                        company=item["postedCompany"]["name"],
                        title=item["title"],
                        url=f"https://www.mycareersfuture.gov.sg/job/{job_uuid}",
                        posted_at=posted_at,
                        ats_type="mycareersfuture",
                        description=description,
                    )
                except (KeyError, IndexError, ValueError, TypeError):
                    logger.warning("Skipping malformed entry: %s", item, exc_info=True)
                    continue

        return list(results.values())
