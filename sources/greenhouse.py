"""Greenhouse Job Board source — pulls roles from large fintechs that host on Greenhouse.

Greenhouse exposes a free, no-auth public Job Board API per company:
    GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true

Banks mostly run Workday/Taleo, but most large fintechs publish on Greenhouse, so this
widens the net beyond MyCareersFuture (SG) + LinkedIn. Jobs are filtered client-side by
title keywords (the API has no server-side search), optional location, and age.

`http_get` is injectable so tests never hit the network. Companies with a different board
token (or that use Lever/Ashby instead) simply 404 and are skipped.
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx

from models import RawJob
from sources.base import JobSource

logger = logging.getLogger(__name__)

_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

# Verified-live Greenhouse boards for large fintechs (token -> display name).
DEFAULT_FINTECH_BOARDS: dict[str, str] = {
    "stripe": "Stripe",
    "coinbase": "Coinbase",
    "block": "Block",
    "adyen": "Adyen",
    "brex": "Brex",
    "affirm": "Affirm",
    "ripple": "Ripple",
    "robinhood": "Robinhood",
    "sofi": "SoFi",
    "chime": "Chime",
    "gocardless": "GoCardless",
    "thunes": "Thunes",
    "marqeta": "Marqeta",
    "blockchain": "Blockchain.com",
}

# Title keywords that flag a Data/AI leadership-ish role (client-side filter).
_DEFAULT_TITLE_KEYWORDS = [
    "data", "analytics", "machine learning", "ml ", "ai ", "artificial intelligence",
    "data science", "data engineer", "head of data", "analytics lead", "data platform",
]


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def _default_http_get(url: str) -> dict:
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


class GreenhouseSource(JobSource):
    def __init__(
        self,
        boards: dict[str, str] | None = None,
        title_keywords: list[str] | None = None,
        location_contains: str | None = None,
        max_age_days: int = 7,
        http_get: Callable[[str], dict] | None = None,
    ) -> None:
        self.boards = boards if boards is not None else DEFAULT_FINTECH_BOARDS
        self.title_keywords = [k.lower() for k in (title_keywords or _DEFAULT_TITLE_KEYWORDS)]
        self.location_contains = location_contains.lower() if location_contains else None
        self.max_age_days = max_age_days
        self.http_get = http_get if http_get is not None else _default_http_get

    def _matches_title(self, title: str) -> bool:
        t = title.lower()
        return any(k in t for k in self.title_keywords)

    def _matches_location(self, location: str) -> bool:
        return self.location_contains is None or self.location_contains in (location or "").lower()

    @staticmethod
    def _parse_dt(raw: str | None) -> datetime | None:
        """Parse Greenhouse's ISO timestamp to a naive-UTC datetime (matches the rest
        of the pipeline, which compares against a naive datetime.now())."""
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt

    def fetch(self) -> list[RawJob]:
        results: list[RawJob] = []
        cutoff = datetime.now() - timedelta(days=self.max_age_days)

        for board, company in self.boards.items():
            try:
                data = self.http_get(_JOBS_URL.format(board=board))
            except Exception:
                logger.warning("Greenhouse board failed (skipping): %s", board, exc_info=True)
                continue

            for job in data.get("jobs", []):
                try:
                    title = job["title"]
                    if not self._matches_title(title):
                        continue
                    location = (job.get("location") or {}).get("name", "")
                    if not self._matches_location(location):
                        continue
                    posted_at = self._parse_dt(job.get("updated_at"))
                    if posted_at is not None and posted_at < cutoff:
                        continue
                    results.append(RawJob(
                        source="greenhouse",
                        company=company,
                        title=title,
                        url=job.get("absolute_url", ""),
                        posted_at=posted_at,
                        ats_type="greenhouse",
                        description=_strip_html(job.get("content", "")),
                    ))
                except (KeyError, TypeError):
                    logger.warning("Skipping malformed Greenhouse entry from %s", board, exc_info=True)
                    continue

        logger.info("Greenhouse: %d roles across %d boards", len(results), len(self.boards))
        return results
