"""Workday source — pulls roles from banks/fintechs hosting on Workday's CxS API.

Workday exposes an unofficial-but-public JSON search per tenant+site:
    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
         body {"limit":20,"offset":0,"searchText":"data","appliedFacets":{}}
    GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}   (full description)

Unlike Greenhouse, Workday is per-tenant: each company needs a verified
{host, tenant, site}. Banks largely run Workday, so this is the source that feeds the
priority-1 target employers. DEFAULT_BANK_TENANTS holds the verified ones; add more as
their site paths are confirmed.

`http_post` / `http_get` are injectable so tests never hit the network.
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable

import httpx

from models import RawJob
from sources.base import JobSource

logger = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"}

# Verified-live Workday tenants (host / tenant / site). Banks mostly run Workday.
DEFAULT_BANK_TENANTS: list[dict[str, str]] = [
    {"company": "Citi", "host": "citi.wd5.myworkdayjobs.com", "tenant": "citi", "site": "2"},
    {"company": "Deutsche Bank", "host": "db.wd3.myworkdayjobs.com", "tenant": "db", "site": "DBWebsite"},
    {"company": "Morgan Stanley", "host": "ms.wd5.myworkdayjobs.com", "tenant": "ms", "site": "External"},
    {"company": "DBS", "host": "dbs.wd3.myworkdayjobs.com", "tenant": "dbs", "site": "DBS_Careers"},
    {"company": "UOB", "host": "uobgroup.wd3.myworkdayjobs.com", "tenant": "uobgroup", "site": "UOBExternal"},
    {"company": "MUFG", "host": "mufgub.wd3.myworkdayjobs.com", "tenant": "mufgub", "site": "MUFG-Careers"},
    {"company": "Mizuho", "host": "mizuhogroup.wd102.myworkdayjobs.com", "tenant": "mizuhogroup", "site": "External"},
    {"company": "Wells Fargo", "host": "wf.wd1.myworkdayjobs.com", "tenant": "wf", "site": "WellsFargoJobs"},
    {"company": "State Street", "host": "statestreet.wd1.myworkdayjobs.com", "tenant": "statestreet", "site": "Global"},
    {"company": "Northern Trust", "host": "ntrs.wd1.myworkdayjobs.com", "tenant": "ntrs", "site": "northerntrust"},
    {"company": "BlackRock", "host": "blackrock.wd1.myworkdayjobs.com", "tenant": "blackrock", "site": "BlackRock_Professional"},
]

_DEFAULT_SEARCH_TERMS = ["data", "analytics", "machine learning", "artificial intelligence"]
_DEFAULT_TITLE_KEYWORDS = ["data", "analytics", "machine learning", "ai ", "artificial intelligence",
                           "data science", "data engineer", "analytics lead", "head of data"]


def _strip_html(text: str) -> str:
    """Convert a Workday HTML job description to compact plain text."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def _default_post(url: str, body: dict) -> dict:
    """Post a Workday CxS search request and decode its JSON response."""
    resp = httpx.post(url, json=body, headers=_HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _default_get(url: str) -> dict:
    """Fetch a Workday CxS detail response as JSON."""
    resp = httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


class WorkdaySource(JobSource):
    """Fetch Singapore-filtered vacancies from configured Workday tenants."""

    def __init__(
        self,
        tenants: list[dict[str, str]] | None = None,
        search_terms: list[str] | None = None,
        title_keywords: list[str] | None = None,
        location_contains: str | None = None,
        limit: int = 20,
        enrich: bool = True,
        http_post: Callable[[str, dict], dict] | None = None,
        http_get: Callable[[str], dict] | None = None,
    ) -> None:
        """Configure tenants, search filters, enrichment, and injectable HTTP."""
        self.tenants = tenants if tenants is not None else DEFAULT_BANK_TENANTS
        self.search_terms = search_terms or _DEFAULT_SEARCH_TERMS
        self.title_keywords = [k.lower() for k in (title_keywords or _DEFAULT_TITLE_KEYWORDS)]
        self.location_contains = location_contains.lower() if location_contains else None
        self.limit = limit
        self.enrich = enrich
        self.http_post = http_post if http_post is not None else _default_post
        self.http_get = http_get if http_get is not None else _default_get

    def _matches_title(self, title: str) -> bool:
        """Return whether a title contains a configured target keyword."""
        t = title.lower()
        return any(k in t for k in self.title_keywords)

    def _matches_location(self, location: str) -> bool:
        """Return whether a posting satisfies the configured location filter."""
        return self.location_contains is None or self.location_contains in (location or "").lower()

    def _description(self, base: str, external_path: str) -> str:
        """Fetch and normalize a Workday posting's full description."""
        try:
            d = self.http_get(f"{base}{external_path}")
        except Exception:
            logger.warning("Workday detail fetch failed for %s", external_path, exc_info=True)
            return ""
        return _strip_html((d.get("jobPostingInfo") or {}).get("jobDescription", ""))

    def fetch(self) -> list[RawJob]:
        """Fetch, filter, enrich, and URL-deduplicate Workday vacancies."""
        results: dict[str, RawJob] = {}
        for cfg in self.tenants:
            base = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}"
            for term in self.search_terms:
                try:
                    data = self.http_post(f"{base}/jobs",
                                          {"limit": self.limit, "offset": 0,
                                           "searchText": term, "appliedFacets": {}})
                except Exception:
                    logger.warning("Workday search failed: %s (%s)", cfg["company"], term, exc_info=True)
                    continue
                for jp in data.get("jobPostings", []):
                    ext = jp.get("externalPath", "")
                    if not ext:
                        continue
                    url = f"https://{cfg['host']}/{cfg['site']}{ext}"
                    if url in results:
                        continue
                    title = jp.get("title", "")
                    if not self._matches_title(title):
                        continue
                    if not self._matches_location(jp.get("locationsText", "")):
                        continue
                    results[url] = RawJob(
                        source="workday",
                        company=cfg["company"],
                        title=title,
                        url=url,
                        posted_at=None,  # CxS list gives only a relative "Posted N days ago"
                        ats_type="workday",
                        description=self._description(base, ext) if self.enrich else "",
                    )
        logger.info("Workday: %d roles across %d tenants", len(results), len(self.tenants))
        return list(results.values())
