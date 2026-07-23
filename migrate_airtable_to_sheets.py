"""One-time migration: pull every record out of the Airtable base and write it into
the Google Sheets tracker (Jobs + Contacts + Outreach tabs).

Reads from Airtable using AIRTABLE_TOKEN / AIRTABLE_BASE_ID (+ table-name env vars),
writes to Google Sheets using GOOGLE_SERVICE_ACCOUNT_JSON + SPREADSHEET_ID. Safe to
re-run: every write is an upsert keyed by the same identifiers the live pipeline uses,
so rows are updated in place rather than duplicated.

    python migrate_airtable_to_sheets.py
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import httpx

from models import Contact, EmailDraft, Job
from store.google_sheets_repo import GoogleSheetsRepository

logger = logging.getLogger("migrate")

_AIRTABLE_BASE = "https://api.airtable.com/v0"


def _fetch_all(token: str, base_id: str, table: str) -> list[dict]:
    """Return every record ({id, fields}) from an Airtable table, following pagination."""
    records: list[dict] = []
    offset: str | None = None
    url = f"{_AIRTABLE_BASE}/{base_id}/{table}"
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        params: dict[str, str | int] = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            return records


def _parse_date(value: str | None) -> datetime | None:
    """Parse an Airtable date value, returning None when absent or invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10])
    except ValueError:
        return None


def _build_sheets() -> GoogleSheetsRepository:
    """Build the destination Sheets repository from environment credentials."""
    sa = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    if os.path.exists(sa):
        return GoogleSheetsRepository.from_service_account_file(sa, spreadsheet_id)
    return GoogleSheetsRepository.from_service_account_info(json.loads(sa), spreadsheet_id)


def migrate() -> dict[str, int]:
    """Migrate Airtable jobs, contacts, and outreach into Google Sheets."""
    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    token = os.environ["AIRTABLE_TOKEN"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    jobs_table = os.environ.get("AIRTABLE_JOBS_TABLE", "Jobs")
    contacts_table = os.environ.get("AIRTABLE_CONTACTS_TABLE", "Contacts")
    outreach_table = os.environ.get("AIRTABLE_OUTREACH_TABLE", "Outreach")

    sheets = _build_sheets()
    counts = {"jobs": 0, "contacts": 0, "outreach": 0}

    # Maps Airtable record id -> the key we store in Sheets, so Outreach links resolve.
    job_key_by_recid: dict[str, str] = {}
    contact_key_by_recid: dict[str, str] = {}

    # ── Jobs ──────────────────────────────────────────────────────────────────
    for rec in _fetch_all(token, base_id, jobs_table):
        f = rec.get("fields", {})
        dedupe_key = f.get("DedupeKey") or f"{f.get('Company','')}|{f.get('Title','')}|{f.get('URL','')}".lower()
        job = Job(
            id=str(uuid.uuid4()),
            source=f.get("Source", "airtable"),
            company_canonical=f.get("Company", ""),
            dedupe_key=dedupe_key,
            title=f.get("Title", ""),
            url=f.get("URL", ""),
            description=f.get("Description", "") or "",
            score=f.get("Score"),
            tier=f.get("Tier"),
            status=f.get("Status", "new") or "new",
            posted_at=_parse_date(f.get("Posted")),
        )
        job_key_by_recid[rec["id"]] = sheets.upsert_job(job)
        counts["jobs"] += 1

    # ── Contacts ──────────────────────────────────────────────────────────────
    for rec in _fetch_all(token, base_id, contacts_table):
        f = rec.get("fields", {})
        contact = Contact(
            id=str(uuid.uuid4()),
            name=f.get("Name", "") or "",
            company_canonical=f.get("Company", "") or "",
            role=f.get("Role", "") or "",
            role_type=f.get("Type", "") or "",
            linkedin_url=f.get("LinkedIn", "") or "",
            email=f.get("Email", "") or "",
            confidence=int(f.get("Confidence") or 0),
        )
        contact_key_by_recid[rec["id"]] = sheets.upsert_contact(contact)
        counts["contacts"] += 1

    # ── Outreach (resolve Job/Contact links to their Sheets keys) ─────────────
    for rec in _fetch_all(token, base_id, outreach_table):
        f = rec.get("fields", {})
        job_link = (f.get("Job") or [""])[0]
        contact_link = (f.get("Contact") or [""])[0]
        draft = EmailDraft(
            job_id="",
            company="",
            to_email=f.get("To", "") or "",
            to_name="",
            role_type="",
            subject=f.get("Subject", "") or "",
            body=f.get("Body", "") or "",
        )
        sheets.record_outreach(
            draft,
            job_key_by_recid.get(job_link),
            contact_key_by_recid.get(contact_link),
        )
        counts["outreach"] += 1

    logger.info("Migration complete: %s", counts)
    return counts


if __name__ == "__main__":
    print(migrate())
