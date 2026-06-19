"""Airtable as the visible job board. Writes Job records to the Jobs table, deduped by
DedupeKey. HTTP is injectable for tests; live when AIRTABLE_TOKEN + AIRTABLE_BASE_ID are set.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote

import httpx

from models import Job

logger = logging.getLogger(__name__)

HttpFn = Callable[[str, str, dict | None], dict]  # (method, url, json_body) -> response
_BASE = "https://api.airtable.com/v0"


class AirtableRepository:
    def __init__(
        self,
        token: str,
        base_id: str,
        jobs_table: str = "Jobs",
        http: HttpFn | None = None,
    ) -> None:
        self.token = token
        self.base_id = base_id
        self.jobs_table = jobs_table
        self.http = http or self._default_http

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _table_url(self) -> str:
        return f"{_BASE}/{self.base_id}/{quote(self.jobs_table)}"

    def _job_fields(self, job: Job) -> dict:
        fields = {
            "Title": job.title,
            "Company": job.company_canonical,
            "URL": job.url,
            "Description": (job.description or "")[:90000],
            "Score": job.score,
            "Status": job.status,
            "Source": job.source,
            "DedupeKey": job.dedupe_key,
        }
        if job.tier in ("A", "B"):  # singleSelect — only send valid choices
            fields["Tier"] = job.tier
        if job.posted_at is not None:
            fields["Posted"] = job.posted_at.date().isoformat()
        return {k: v for k, v in fields.items() if v is not None}

    def _find_by_dedupe(self, dedupe_key: str) -> str | None:
        formula = quote(f"{{DedupeKey}}='{dedupe_key}'")
        url = f"{self._table_url()}?filterByFormula={formula}&maxRecords=1"
        records = self.http("GET", url, None).get("records", [])
        return records[0]["id"] if records else None

    def upsert_job(self, job: Job) -> str:
        existing = self._find_by_dedupe(job.dedupe_key)
        fields = self._job_fields(job)
        if existing:
            self.http("PATCH", self._table_url(),
                      {"records": [{"id": existing, "fields": fields}]})
            return existing
        res = self.http("POST", self._table_url(), {"records": [{"fields": fields}]})
        return res["records"][0]["id"]
