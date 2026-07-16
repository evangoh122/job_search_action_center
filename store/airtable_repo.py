"""Airtable as the visible job board + contact/outreach tracker.

Three tables (schema discovered live):
  Jobs:     Title, Company, URL, Description, Score, Tier(A|B), Status, Posted,
            Source, DedupeKey, Outreach(link)
  Contacts: Name, Email, Company, Role, Type(recruiter|hiring_manager), LinkedIn,
            Confidence, Outreach(link)
  Outreach: Subject, Body, To, Status(drafted|sent|opened|replied), Date,
            Job(link), Contact(link)

HTTP is injectable for tests; live when AIRTABLE_TOKEN + AIRTABLE_BASE_ID are set.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

import httpx

from models import Contact, EmailDraft, Job

logger = logging.getLogger(__name__)

HttpFn = Callable[[str, str, dict | None], dict]  # (method, url, json_body) -> response
_BASE = "https://api.airtable.com/v0"

_CONTACT_TYPES = {"recruiter", "hiring_manager"}  # Type singleSelect options


def _drop_empty(fields: dict) -> dict:
    """Airtable rejects empty strings for url/email/select fields — drop blanks (keep 0)."""
    return {k: v for k, v in fields.items() if v is not None and v != ""}


class AirtableRepository:
    """Persist jobs, contacts, and outreach drafts in Airtable tables."""

    def __init__(
        self,
        token: str,
        base_id: str,
        jobs_table: str = "Jobs",
        contacts_table: str = "Contacts",
        outreach_table: str = "Outreach",
        http: HttpFn | None = None,
    ) -> None:
        """Configure Airtable credentials, table names, and HTTP transport."""
        self.token = token
        self.base_id = base_id
        self.jobs_table = jobs_table
        self.contacts_table = contacts_table
        self.outreach_table = outreach_table
        self.http = http or self._default_http

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        """Perform an authenticated Airtable JSON request."""
        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── low-level helpers ────────────────────────────────────────────────────
    def _table_url(self, table: str) -> str:
        """Return the encoded Airtable endpoint for a table."""
        return f"{_BASE}/{self.base_id}/{quote(table)}"

    @staticmethod
    def _eq(field: str, value: str) -> str:
        """Build a simple escaped Airtable equality formula."""
        safe = str(value).replace('"', " ")  # avoid breaking the formula string
        return f'{{{field}}}="{safe}"'

    def _find(self, table: str, formula: str) -> str | None:
        """Find the first record identifier matching a formula."""
        url = f"{self._table_url(table)}?filterByFormula={quote(formula)}&maxRecords=1"
        records = self.http("GET", url, None).get("records", [])
        return records[0]["id"] if records else None

    def _create(self, table: str, fields: dict) -> str:
        """Create an Airtable record and return its identifier."""
        res = self.http("POST", self._table_url(table), {"records": [{"fields": fields}]})
        return res["records"][0]["id"]

    def _update(self, table: str, rec_id: str, fields: dict) -> str:
        """Update an Airtable record and return its identifier."""
        self.http("PATCH", self._table_url(table),
                  {"records": [{"id": rec_id, "fields": fields}]})
        return rec_id

    def _upsert(self, table: str, formula: str, fields: dict) -> str:
        """Create or update a record selected by an Airtable formula."""
        existing = self._find(table, formula)
        return self._update(table, existing, fields) if existing else self._create(table, fields)

    # ── Jobs ─────────────────────────────────────────────────────────────────
    def _job_fields(self, job: Job) -> dict:
        """Map a job to non-empty Airtable fields."""
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
        return _drop_empty(fields)

    def upsert_job(self, job: Job) -> str:
        """Upsert a job by its stable deduplication key."""
        return self._upsert(self.jobs_table, self._eq("DedupeKey", job.dedupe_key),
                            self._job_fields(job))

    # ── Contacts ───────────────────────────────────────────────────────────────
    def _contact_fields(self, c: Contact) -> dict:
        """Map a contact to non-empty Airtable fields."""
        fields = {
            "Name": c.name,
            "Email": c.email,
            "Company": c.company_canonical,
            "Role": c.role,
            "LinkedIn": c.linkedin_url,
            "Confidence": c.confidence,
        }
        if c.role_type in _CONTACT_TYPES:  # singleSelect — only valid choices
            fields["Type"] = c.role_type
        return _drop_empty(fields)

    def upsert_contact(self, c: Contact) -> str:
        """Upsert a contact using email, LinkedIn URL, or name."""
        # Dedupe by the strongest identifier available: email > linkedin > name.
        if c.email:
            formula = self._eq("Email", c.email)
        elif c.linkedin_url:
            formula = self._eq("LinkedIn", c.linkedin_url)
        else:
            formula = self._eq("Name", c.name)
        return self._upsert(self.contacts_table, formula, self._contact_fields(c))

    # ── Outreach ───────────────────────────────────────────────────────────────
    def record_outreach(
        self,
        draft: EmailDraft,
        job_record_id: str | None = None,
        contact_record_id: str | None = None,
    ) -> str:
        """Log one outreach email, linked to its Job + Contact records when known."""
        fields = {
            "Subject": draft.subject,
            "Body": draft.body,
            "To": draft.to_email,
            "Status": "drafted",
            "Date": datetime.now().date().isoformat(),
        }
        if job_record_id:
            fields["Job"] = [job_record_id]
        if contact_record_id:
            fields["Contact"] = [contact_record_id]
        # Dedupe by recipient + subject (no stable key field on the table).
        formula = f'AND({self._eq("To", draft.to_email)}, {self._eq("Subject", draft.subject)})'
        return self._upsert(self.outreach_table, formula, _drop_empty(fields))
