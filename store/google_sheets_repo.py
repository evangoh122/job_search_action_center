"""Google Sheets as the visible job board + contact/outreach tracker.

Drop-in replacement for the former Airtable tracker. One spreadsheet, three tabs
(auto-created with header rows on first use):

  Jobs:     DedupeKey, Title, Company, URL, Score, Tier, Status, Source, Posted, Description
  Contacts: Key, Name, Email, Company, Role, Type, LinkedIn, Confidence
  Outreach: Key, Subject, Body, To, Status, Date, Job, Contact

The three job-application tabs above are coloured green. A fourth tab, "Networking
Tracker" (orange), holds networking contacts pulled from Gmail:

  Networking Tracker: Key, Name, Email, Company, Role, LinkedIn, Source, Last Contacted,
                      Status, Notes

Sheets has no native record links, so cross-tab references are plain key values:
Outreach.Job = Jobs.DedupeKey, Outreach.Contact = Contacts.Key. Each tab is upserted
by its leading key column (column A).

HTTP is injectable for tests; live calls use a service-account bearer token
(see from_service_account_file / from_service_account_info). Auth needs the
spreadsheets scope and the spreadsheet shared with the service-account email.
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
_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

JOBS_HEADERS = ["DedupeKey", "Title", "Company", "URL", "Score", "Tier",
                "Status", "Source", "Posted", "Description", "Aging", "Applied"]
CONTACTS_HEADERS = ["Key", "Name", "Email", "Company", "Role", "Type",
                    "LinkedIn", "Confidence"]
OUTREACH_HEADERS = ["Key", "Subject", "Body", "To", "Status", "Date", "Job", "Contact"]
NETWORKING_HEADERS = ["Key", "Name", "Email", "Company", "Role", "LinkedIn",
                      "Source", "Last Contacted", "Status", "Notes"]

_CONTACT_TYPES = {"recruiter", "hiring_manager"}  # Type column allowed values
_MAX_CELL = 40000  # Sheets caps a cell at 50k chars; stay well under

# Tab colours (RGB 0-1). Job-application tabs green; networking tab orange.
_GREEN = {"red": 0.20, "green": 0.66, "blue": 0.33}
_ORANGE = {"red": 0.95, "green": 0.55, "blue": 0.16}


def _col_letter(n: int) -> str:
    """1-based column index -> A1 letter (1 -> A). Sufficient for <=26-column tabs."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class GoogleSheetsRepository:
    def __init__(
        self,
        spreadsheet_id: str,
        token: str = "",
        jobs_tab: str = "Jobs",
        contacts_tab: str = "Contacts",
        outreach_tab: str = "Outreach",
        networking_tab: str = "Networking Tracker",
        http: HttpFn | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.token = token
        self.jobs_tab = jobs_tab
        self.contacts_tab = contacts_tab
        self.outreach_tab = outreach_tab
        self.networking_tab = networking_tab
        self.http = http or self._default_http
        # Tab -> header row, in column order. Used for bootstrapping and row width.
        self._headers_by_tab = {
            jobs_tab: JOBS_HEADERS,
            contacts_tab: CONTACTS_HEADERS,
            outreach_tab: OUTREACH_HEADERS,
            networking_tab: NETWORKING_HEADERS,
        }
        # Job-application tabs green; networking tab orange.
        self._tab_colors = {
            jobs_tab: _GREEN,
            contacts_tab: _GREEN,
            outreach_tab: _GREEN,
            networking_tab: _ORANGE,
        }
        self._ready = False  # tabs + headers ensured?
        self._sheet_ids: dict[str, int] = {}  # tab title -> sheetId (filled by _ensure_ready)
        self.last_was_new = False  # was the most recent upsert a new append?

    # ── auth constructors ────────────────────────────────────────────────────
    @classmethod
    def from_service_account_file(cls, path: str, spreadsheet_id: str, **kw) -> "GoogleSheetsRepository":
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(path, scopes=_SCOPES)
        creds.refresh(Request())
        return cls(spreadsheet_id, token=creds.token, **kw)

    @classmethod
    def from_service_account_info(cls, info: dict, spreadsheet_id: str, **kw) -> "GoogleSheetsRepository":
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        creds.refresh(Request())
        return cls(spreadsheet_id, token=creds.token, **kw)

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # ── low-level Sheets helpers ─────────────────────────────────────────────
    def _url(self, suffix: str = "") -> str:
        return f"{_BASE}/{self.spreadsheet_id}{suffix}"

    def _values_get(self, a1: str) -> list[list]:
        return self.http("GET", self._url(f"/values/{quote(a1)}"), None).get("values", [])

    def _values_update(self, a1: str, row: list) -> None:
        self.http("PUT", self._url(f"/values/{quote(a1)}?valueInputOption=RAW"), {"values": [row]})

    def _values_append(self, tab: str, row: list) -> None:
        a1 = quote(f"'{tab}'!A1")
        url = self._url(f"/values/{a1}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
        self.http("POST", url, {"values": [row]})

    def _ensure_ready(self) -> None:
        """Create any missing tabs and write header rows. Runs once per instance."""
        if self._ready:
            return
        meta = self.http("GET", self._url(), None)
        existing = {s["properties"]["title"]: s["properties"]["sheetId"]
                    for s in meta.get("sheets", [])}
        self._sheet_ids = dict(existing)
        requests: list[dict] = []
        for tab, color in self._tab_colors.items():
            if tab in existing:  # recolour in place
                requests.append({"updateSheetProperties": {
                    "properties": {"sheetId": existing[tab], "tabColor": color},
                    "fields": "tabColor",
                }})
            else:  # create with colour
                requests.append({"addSheet": {
                    "properties": {"title": tab, "tabColor": color},
                }})
        if requests:
            res = self.http("POST", self._url(":batchUpdate"), {"requests": requests})
            for reply in (res or {}).get("replies", []):
                props = reply.get("addSheet", {}).get("properties")
                if props:
                    self._sheet_ids[props["title"]] = props["sheetId"]
        for tab, headers in self._headers_by_tab.items():
            first = self._values_get(f"'{tab}'!1:1")
            if not first or not first[0] or len(first[0]) < len(headers):
                self._values_update(f"'{tab}'!A1", headers)
        self._ready = True

    def _upsert_row(self, tab: str, key: str, row: list) -> str:
        """Match key in column A (data rows); update that row in place or append. Returns key.
        Sets self.last_was_new = True when the row was newly appended (not previously present)."""
        self._ensure_ready()
        col_a = self._values_get(f"'{tab}'!A2:A")
        match = next((i + 2 for i, cell in enumerate(col_a) if cell and cell[0] == key), None)
        self.last_was_new = match is None
        if match is not None:
            last = _col_letter(len(row))
            self._values_update(f"'{tab}'!A{match}:{last}{match}", row)
        else:
            self._values_append(tab, row)
        return key

    # ── Jobs ─────────────────────────────────────────────────────────────────
    def _job_row(self, job: Job) -> list:
        return [
            job.dedupe_key,
            job.title,
            job.company_canonical,
            job.url,
            job.score if job.score is not None else "",
            job.tier if job.tier in ("A", "B") else "",
            job.status,
            job.source,
            job.posted_at.date().isoformat() if job.posted_at is not None else "",
            (job.description or "")[:_MAX_CELL],
            # Aging (column K) is a live formula managed by refresh_aging_formulas(),
            # not written here — a RAW upsert would overwrite the formula with text.
        ]

    def upsert_job(self, job: Job) -> str:
        return self._upsert_row(self.jobs_tab, job.dedupe_key, self._job_row(job))

    def refresh_aging_formulas(self) -> int:
        """(Re)write the Aging column (K) as live formulas: days since Posted (col I),
        recomputed by the sheet itself via TODAY(). Call after a run / to backfill.
        Returns the number of data rows written."""
        self._ensure_ready()
        n = len(self._values_get(f"'{self.jobs_tab}'!A2:A"))
        if n == 0:
            return 0
        # One formula per data row (rows 2..n+1); blank Posted -> blank Aging.
        formulas = [[f'=IF($I{r}="","",TODAY()-DATEVALUE($I{r}))'] for r in range(2, n + 2)]
        a1 = quote(f"'{self.jobs_tab}'!K2:K{n + 1}")
        self.http("PUT", self._url(f"/values/{a1}?valueInputOption=USER_ENTERED"),
                  {"values": formulas})
        # Show Aging as a whole number (avoid the sheet's inherited 2-decimal date format).
        sid = self._sheet_ids.get(self.jobs_tab)
        if sid is not None:
            self.http("POST", self._url(":batchUpdate"), {"requests": [{"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": 10,
                          "endColumnIndex": 11},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0"}}},
                "fields": "userEnteredFormat.numberFormat",
            }}]})
        return n

    def sort_jobs(self) -> None:
        """Sort the Jobs tab by Score (Z-A) then Aging (A-Z)."""
        self._ensure_ready()
        sid = self._sheet_ids.get(self.jobs_tab)
        if sid is None:
            return
        
        request = {
            "sortRange": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 26  # Extend to cover user-added columns up to Z
                },
                "sortSpecs": [
                    {
                        "dimensionIndex": 11,  # Applied column (L)
                        "sortOrder": "ASCENDING"
                    },
                    {
                        "dimensionIndex": 4,  # Score column
                        "sortOrder": "DESCENDING"
                    },
                    {
                        "dimensionIndex": 10,  # Aging column
                        "sortOrder": "ASCENDING"
                    }
                ]
            }
        }
        self.http("POST", self._url(":batchUpdate"), {"requests": [request]})

    # ── Contacts ─────────────────────────────────────────────────────────────
    @staticmethod
    def _contact_key(c: Contact) -> str:
        # Strongest identifier available: email > linkedin > name.
        return c.email or c.linkedin_url or c.name

    def _contact_row(self, c: Contact, key: str) -> list:
        return [
            key,
            c.name,
            c.email,
            c.company_canonical,
            c.role,
            c.role_type if c.role_type in _CONTACT_TYPES else "",
            c.linkedin_url,
            c.confidence,
        ]

    def upsert_contact(self, c: Contact) -> str:
        key = self._contact_key(c)
        return self._upsert_row(self.contacts_tab, key, self._contact_row(c, key))

    # ── Outreach ─────────────────────────────────────────────────────────────
    def record_outreach(
        self,
        draft: EmailDraft,
        job_key: str | None = None,
        contact_key: str | None = None,
    ) -> str:
        """Log one outreach email, referencing its Job + Contact keys when known."""
        key = f"{draft.to_email}|{draft.subject}"  # dedupe by recipient + subject
        row = [
            key,
            draft.subject,
            draft.body,
            draft.to_email,
            "drafted",
            datetime.now().date().isoformat(),
            job_key or "",
            contact_key or "",
        ]
        return self._upsert_row(self.outreach_tab, key, row)

    # ── Networking Tracker ───────────────────────────────────────────────────
    def upsert_networking(
        self,
        name: str,
        email: str = "",
        company: str = "",
        role: str = "",
        linkedin: str = "",
        source: str = "gmail",
        last_contacted: str = "",
        status: str = "new",
        notes: str = "",
    ) -> str:
        """Add/update a networking contact (e.g. scraped from Gmail). Keyed by email or name."""
        key = email or name
        row = [key, name, email, company, role, linkedin,
               source, last_contacted, status, notes]
        return self._upsert_row(self.networking_tab, key, row)

    # ── Backup ───────────────────────────────────────────────────────────────
    def export_tab(self, tab: str) -> list[list]:
        """Return every value (incl. header row) currently in a tab."""
        return self._values_get(f"'{tab}'!A1:ZZ")

    def _titles(self, spreadsheet_id: str) -> set[str]:
        meta = self.http("GET", f"{_BASE}/{spreadsheet_id}", None)
        return {s["properties"]["title"] for s in meta.get("sheets", [])}

    def snapshot_to(self, backup_spreadsheet_id: str, suffix: str | None = None) -> list[str]:
        """Copy every tab's current values into date-stamped tabs in a backup spreadsheet.

        The backup spreadsheet must already exist and be shared with the same credentials.
        Re-running on the same day overwrites that day's snapshot tabs. Returns tab names written.
        """
        suffix = suffix or datetime.now().date().isoformat()
        existing = self._titles(backup_spreadsheet_id)
        written: list[str] = []
        for tab in self._headers_by_tab:
            values = self.export_tab(tab)
            if not values:
                continue
            title = f"{tab} {suffix}"
            if title not in existing:
                self.http("POST", f"{_BASE}/{backup_spreadsheet_id}:batchUpdate",
                          {"requests": [{"addSheet": {"properties": {"title": title}}}]})
            a1 = quote(f"'{title}'!A1")
            self.http("PUT",
                      f"{_BASE}/{backup_spreadsheet_id}/values/{a1}?valueInputOption=RAW",
                      {"values": values})
            written.append(title)
        return written
