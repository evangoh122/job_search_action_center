"""HubSpot CRM as the tracking backbone, behind the Repository interface.

Jobs are stored as Deals (full Job JSON in a `job_data` property, deduped by `dedupe_key`),
contacts as Contacts. Daily-cap counters delegate to a local SqliteRepository (HubSpot is not a
counter store). HTTP is injectable so tests never hit the network; live when a token is set.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import httpx

from models import Contact, Job
from store.repository import Repository, SqliteRepository

logger = logging.getLogger(__name__)

# These custom properties must exist on the HubSpot Deal (and `contact_id`/`role` on Contact)
# before live use — create them once in HubSpot settings or via the properties API:
#   Deal:    dedupe_key, job_id, job_data, job_score, job_tier, job_status
#   Contact: contact_id, role
REQUIRED_DEAL_PROPS = ("dedupe_key", "job_id", "job_data", "job_score", "job_tier", "job_status")

# (method, url, json_body) -> response dict
HttpFn = Callable[[str, str, dict | None], dict]
_BASE = "https://api.hubapi.com"


class HubSpotRepository(Repository):
    """Persist jobs and contacts in HubSpot with local action counters."""

    def __init__(
        self,
        token: str,
        http: HttpFn | None = None,
        counter: Repository | None = None,
    ) -> None:
        """Configure HubSpot authentication, HTTP transport, and counters."""
        self.token = token
        self.http = http or self._default_http
        self.counter = counter or SqliteRepository(":memory:")

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        """Perform a HubSpot request with bounded rate-limit retries."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        for attempt in range(3):
            resp = httpx.request(method, url, headers=headers, json=body, timeout=30)
            if resp.status_code == 429 and attempt < 2:  # rate-limited — back off and retry
                wait = float(resp.headers.get("Retry-After", 2**attempt))
                logger.warning("HubSpot 429; retrying in %ss", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("HubSpot request failed after retries")

    def _job_props(self, job: Job) -> dict:
        """Serialize a job into configured HubSpot deal properties."""
        return {
            "dealname": job.title,
            "dedupe_key": job.dedupe_key,
            "job_id": job.id,
            "job_data": job.model_dump_json(),
            "job_score": job.score,
            "job_tier": job.tier or "",
            "job_status": job.status,
        }

    def _search_deal(self, prop: str, value: str) -> dict | None:
        """Find the first HubSpot deal matching one property value."""
        body = {
            "filterGroups": [{"filters": [{"propertyName": prop, "operator": "EQ", "value": value}]}],
            "properties": ["dedupe_key", "job_id", "job_data"],
        }
        res = self.http("POST", f"{_BASE}/crm/v3/objects/deals/search", body)
        results = res.get("results", [])
        return results[0] if results else None

    def upsert_job(self, job: Job) -> None:
        """Create or replace the HubSpot deal for a vacancy key."""
        existing = self._search_deal("dedupe_key", job.dedupe_key)
        props = {"properties": self._job_props(job)}
        if existing:
            self.http("PATCH", f"{_BASE}/crm/v3/objects/deals/{existing['id']}", props)
        else:
            self.http("POST", f"{_BASE}/crm/v3/objects/deals", props)

    def get_job(self, job_id: str) -> Job | None:
        """Return one job stored in HubSpot by application job identifier."""
        found = self._search_deal("job_id", job_id)
        if not found:
            return None
        data = found.get("properties", {}).get("job_data")
        return Job.model_validate_json(data) if data else None

    def list_jobs(self) -> list[Job]:
        """Page through and decode all valid HubSpot job deals."""
        out: list[Job] = []
        url: str | None = f"{_BASE}/crm/v3/objects/deals?limit=100&properties=job_data"
        while url:
            res = self.http("GET", url, None)
            for r in res.get("results", []):
                data = r.get("properties", {}).get("job_data")
                if not data:
                    continue
                try:
                    out.append(Job.model_validate_json(data))
                except (ValueError, json.JSONDecodeError):
                    logger.warning("bad job_data in deal %s", r.get("id"))
            after = res.get("paging", {}).get("next", {}).get("after")
            url = (
                f"{_BASE}/crm/v3/objects/deals?limit=100&properties=job_data&after={after}"
                if after
                else None
            )
        return out

    def upsert_contact(self, c: Contact) -> None:
        """Create or update an email-addressed HubSpot contact."""
        # The Gmail Sales extension attaches open-tracking by matching the recipient email,
        # so a contact with no email is useless here — skip it. Uses only standard HubSpot
        # properties (email/firstname/company/jobtitle) to avoid custom-property setup.
        if not c.email:
            return
        body = {
            "filterGroups": [
                {"filters": [{"propertyName": "email", "operator": "EQ", "value": c.email}]}
            ],
            "properties": ["email"],
        }
        res = self.http("POST", f"{_BASE}/crm/v3/objects/contacts/search", body)
        results = res.get("results", [])
        props = {
            "properties": {
                k: v for k, v in {
                    "email": c.email,
                    "firstname": c.name,
                    "company": c.company_canonical,
                    "jobtitle": c.role,
                }.items() if v
            }
        }
        if results:
            self.http("PATCH", f"{_BASE}/crm/v3/objects/contacts/{results[0]['id']}", props)
        else:
            self.http("POST", f"{_BASE}/crm/v3/objects/contacts", props)

    def incr_action(self, kind: str, day: str) -> int:
        """Increment a day-scoped action counter in the delegated store."""
        return self.counter.incr_action(kind, day)

    def count_actions(self, kind: str, day: str) -> int:
        """Return a day-scoped action count from the delegated store."""
        return self.counter.count_actions(kind, day)
