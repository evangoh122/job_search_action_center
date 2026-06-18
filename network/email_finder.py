from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from models import Contact

logger = logging.getLogger(__name__)

HttpGet = Callable[[str], dict]  # url -> json dict

_RECRUITER_KW = ("recruit", "talent", "people", "staffing", "sourcer")
_MANAGER_KW = ("manager", "lead", "head", "director", "vp", "chief", "principal")


def _classify(position: str, department: str) -> str | None:
    p = (position or "").lower()
    d = (department or "").lower()
    if "hr" in d or "human res" in d or any(k in p for k in _RECRUITER_KW):
        return "recruiter"
    if any(k in p for k in _MANAGER_KW):
        return "hiring_manager"
    return None


class HunterEmailFinder:
    """Finds recruiter + hiring-manager emails via Hunter.io Domain Search.

    `http_get` is injectable so tests never hit the network. Needs `HUNTER_API_KEY` for live use.
    """

    def __init__(self, api_key: str, http_get: HttpGet | None = None):
        self.api_key = api_key
        self.http_get = http_get or self._default_get

    def _default_get(self, url: str) -> dict:
        r = httpx.get(url, timeout=30)
        r.raise_for_status()
        return r.json()

    def find_people(self, company: str, max_each: int = 1) -> list[Contact]:
        """Up to max_each recruiters and max_each hiring managers, highest confidence first."""
        url = (
            f"https://api.hunter.io/v2/domain-search?company={company}&api_key={self.api_key}"
        )
        try:
            data = self.http_get(url)
        except Exception:
            logger.warning("Hunter lookup failed for %s", company, exc_info=True)
            return []

        emails = data.get("data", {}).get("emails", [])
        buckets: dict[str, list[Contact]] = {"recruiter": [], "hiring_manager": []}

        for e in emails:
            rt = _classify(e.get("position", ""), e.get("department", ""))
            if rt is None:
                continue
            name = f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()
            buckets[rt].append(
                Contact(
                    id=e["value"],
                    name=name or e["value"],
                    company_canonical=company,
                    role=e.get("position", ""),
                    role_type=rt,
                    email=e["value"],
                    confidence=int(e.get("confidence", 0) or 0),
                )
            )

        out: list[Contact] = []
        for rt in ("recruiter", "hiring_manager"):
            out.extend(sorted(buckets[rt], key=lambda c: c.confidence, reverse=True)[:max_each])
        return out
