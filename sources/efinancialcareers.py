"""eFinancialCareers source for finance-focused Data/AI roles.

The site does not expose a stable public API, so this source uses regular search pages
and parses structured job data from the returned HTML. HTTP is injectable so tests never
hit the network; failures are isolated like the other job sources.
"""
from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx

from models import RawJob
from salary import extract_salary
from sources.base import JobSource

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.efinancialcareers.sg"
_SEARCH_URL = "https://www.efinancialcareers.sg/jobs/{term}/in-{location}"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

_DEFAULT_TITLE_KEYWORDS = [
    "data",
    "analytics",
    "machine learning",
    "ml ",
    "ai ",
    "artificial intelligence",
    "data science",
    "data engineer",
    "data platform",
    "head of data",
    "analytics lead",
]


def _default_get(url: str) -> str:
    response = httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def _parse_dt(raw: object) -> datetime | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            value = raw / 1000 if raw > 10_000_000_000 else raw
            return datetime.fromtimestamp(value)
        text = str(raw).strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except (OSError, TypeError, ValueError):
        return None


def _iter_json_objects(value: object) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_objects(child)


def _extract_json_ld(html_text: str) -> Iterable[dict]:
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Skipping invalid eFinancialCareers JSON-LD", exc_info=True)
            continue
        for obj in _iter_json_objects(data):
            if obj.get("@type") == "JobPosting":
                yield obj


def _company_name(obj: dict) -> str:
    company = (
        obj.get("company")
        or obj.get("companyName")
        or obj.get("hiringOrganization")
        or obj.get("organization")
    )
    if isinstance(company, dict):
        return str(company.get("name") or company.get("companyName") or "").strip()
    return str(company or "").strip()


def _extract_embedded_json(html_text: str) -> Iterable[dict]:
    """Extract likely job dicts from app-state JSON blocks."""
    pattern = re.compile(r"<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(html_text):
        raw = html.unescape(match.group(1)).strip()
        if not raw or not ("job" in raw.lower() and "title" in raw.lower()):
            continue
        if raw.startswith("window."):
            raw = raw.partition("=")[2].strip().rstrip(";")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in _iter_json_objects(data):
            if obj.get("@type") == "JobPosting":
                continue
            title = obj.get("title") or obj.get("jobTitle") or obj.get("name")
            url = obj.get("url") or obj.get("jobUrl") or obj.get("absoluteUrl")
            if title and url and _company_name(obj):
                yield obj


def _location_text(obj: dict) -> str:
    loc = obj.get("jobLocation") or obj.get("location") or obj.get("locations") or ""
    if isinstance(loc, list):
        return " ".join(_location_text({"location": item}) for item in loc)
    if isinstance(loc, dict):
        address = loc.get("address") or {}
        if isinstance(address, dict):
            return " ".join(str(v) for v in address.values() if v)
        return " ".join(str(v) for v in loc.values() if isinstance(v, str))
    return str(loc or "")


class EFinancialCareersSource(JobSource):
    def __init__(
        self,
        search_terms: list[str],
        location: str = "Singapore",
        title_keywords: list[str] | None = None,
        max_age_days: int = 7,
        http_get: Callable[[str], str] | None = None,
    ) -> None:
        self.search_terms = search_terms
        self.location = location
        self.location_filter = location.lower() if location else None
        self.title_keywords = [k.lower() for k in (title_keywords or _DEFAULT_TITLE_KEYWORDS)]
        self.max_age_days = max_age_days
        self.http_get = http_get if http_get is not None else _default_get

    def _search_url(self, term: str) -> str:
        slug = lambda value: re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return _SEARCH_URL.format(term=slug(term), location=slug(self.location))

    def _matches_title(self, title: str) -> bool:
        t = title.lower()
        return any(k in t for k in self.title_keywords)

    def _matches_location(self, obj: dict) -> bool:
        if self.location_filter is None:
            return True
        text = _location_text(obj).lower()
        return not text or self.location_filter in text

    def _to_job(self, obj: dict) -> RawJob | None:
        title = str(obj.get("title") or obj.get("jobTitle") or obj.get("name") or "").strip()
        company = _company_name(obj)
        url = str(obj.get("url") or obj.get("jobUrl") or obj.get("absoluteUrl") or "").strip()
        if not (title and company and url):
            return None
        if not self._matches_title(title) or not self._matches_location(obj):
            return None

        posted_at = _parse_dt(
            obj.get("datePosted") or obj.get("postedAt") or obj.get("postedDate") or obj.get("createdAt")
        )
        if posted_at is not None and posted_at < datetime.now() - timedelta(days=self.max_age_days):
            return None

        salary = extract_salary(obj)
        return RawJob(
            source="efinancialcareers",
            company=company,
            title=title,
            url=urljoin(_BASE_URL, url),
            posted_at=posted_at,
            ats_type="efinancialcareers",
            description=_strip_html(str(obj.get("description") or obj.get("summary") or "")),
            salary_min=salary.minimum,
            salary_max=salary.maximum,
            salary_currency=salary.currency,
            salary_period=salary.period,
        )

    def fetch(self) -> list[RawJob]:
        results: dict[str, RawJob] = {}
        consecutive_failures = 0
        for term in self.search_terms:
            try:
                page = self.http_get(self._search_url(term))
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.warning("eFinancialCareers fetch failed for term '%s'", term)
                if consecutive_failures >= 3:
                    logger.error("Stopping eFinancialCareers scan after 3 consecutive failures.")
                    break
                continue

            for obj in [*_extract_json_ld(page), *_extract_embedded_json(page)]:
                try:
                    job = self._to_job(obj)
                except Exception:
                    logger.warning("Skipping malformed eFinancialCareers entry: %s", obj, exc_info=True)
                    continue
                if job is not None:
                    results[job.url] = job

        logger.info("eFinancialCareers: fetched %d jobs across %d terms", len(results), len(self.search_terms))
        return list(results.values())
