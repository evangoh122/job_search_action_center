from __future__ import annotations

from datetime import datetime

from models import Contact, EmailDraft, Job
from store.google_sheets_repo import GoogleSheetsRepository


def _job() -> Job:
    return Job(
        id="j1", source="mycareersfuture", company_canonical="DBS",
        dedupe_key="dbs|head of data|u1", title="Head of Data",
        url="https://x/1", description="machine learning Databricks",
        score=88.0, tier="B", posted_at=datetime(2026, 6, 19),
    )


def _repo(http, ready=True) -> GoogleSheetsRepository:
    repo = GoogleSheetsRepository("sheet123", token="tok", http=http)
    repo._ready = ready  # skip tab/header bootstrapping unless a test wants it
    return repo


def _fake(col_a: list | None = None):
    """Fake Sheets HTTP. col_a is the data of the upsert key column (A2:A)."""
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        calls.append((method, url, body))
        if method == "GET" and "A2%3AA" in url:
            return {"values": col_a or []}
        return {}

    return http, calls


def _appended(calls) -> list:
    post = [c for c in calls if c[0] == "POST" and ":append" in c[1]][0]
    return post[2]["values"][0]


def _updated(calls) -> list:
    put = [c for c in calls if c[0] == "PUT"][0]
    return put[2]["values"][0]


# ── Jobs ─────────────────────────────────────────────────────────────────────
def test_upsert_job_creates_when_absent():
    http, calls = _fake([])
    key = _repo(http).upsert_job(_job())
    assert key == "dbs|head of data|u1"
    row = _appended(calls)
    # Aging (col K) is a live formula, not written by the row upsert -> 10 columns.
    assert row == ["dbs|head of data|u1", "Head of Data", "DBS", "https://x/1",
                   88.0, "B", "new", "mycareersfuture", "2026-06-19",
                   "machine learning Databricks"]


def test_refresh_aging_writes_live_formulas():
    # 3 data rows present in column A.
    http, calls = _fake([["k1"], ["k2"], ["k3"]])
    repo = _repo(http)
    repo._sheet_ids = {"Jobs": 0}
    n = repo.refresh_aging_formulas()
    assert n == 3
    put = [c for c in calls if c[0] == "PUT" and "USER_ENTERED" in c[1]][0]
    assert "K2%3AK4" in put[1]  # writes K2:K4 (rows 2..4)
    formulas = [v[0] for v in put[2]["values"]]
    assert formulas[0] == '=IF($I2="","",TODAY()-DATEVALUE($I2))'
    assert formulas[2] == '=IF($I4="","",TODAY()-DATEVALUE($I4))'  # row-relative
    # whole-number format applied to column K
    fmt = [c for c in calls if c[0] == "POST" and ":batchUpdate" in c[1]][-1]
    assert fmt[2]["requests"][0]["repeatCell"]["range"]["startColumnIndex"] == 10


def test_upsert_job_updates_when_present():
    http, calls = _fake([["dbs|head of data|u1"]])
    key = _repo(http).upsert_job(_job())
    assert key == "dbs|head of data|u1"
    put = [c for c in calls if c[0] == "PUT"][0]
    assert "A2%3AJ2" in put[1]  # row 2, columns A..J updated (K/Aging is formula-managed)
    assert not any(":append" in c[1] for c in calls)


def test_tier_none_blank():
    job = _job()
    job.tier = None
    http, calls = _fake([])
    _repo(http).upsert_job(job)
    assert _appended(calls)[5] == ""  # Tier column blank, not "None"


# ── Contacts ─────────────────────────────────────────────────────────────────
def _contact(**kw) -> Contact:
    base = dict(id="c1", name="Jane Tan", company_canonical="DBS", role="Talent Acquisition",
                role_type="recruiter", email="jane@dbs.com", confidence=92)
    base.update(kw)
    return Contact(**base)


def test_upsert_contact_creates_keyed_by_email():
    http, calls = _fake([])
    key = _repo(http).upsert_contact(_contact())
    assert key == "jane@dbs.com"
    row = _appended(calls)
    assert row[0] == "jane@dbs.com"
    assert row[2] == "jane@dbs.com"
    assert row[5] == "recruiter"
    assert row[7] == 92


def test_upsert_contact_invalid_type_blank():
    http, calls = _fake([])
    _repo(http).upsert_contact(_contact(role_type="boss"))
    assert _appended(calls)[5] == ""  # only recruiter|hiring_manager kept


def test_upsert_contact_keys_by_linkedin_when_no_email():
    http, calls = _fake([])
    key = _repo(http).upsert_contact(
        _contact(email="", linkedin_url="https://linkedin.com/in/jane")
    )
    assert key == "https://linkedin.com/in/jane"
    assert _appended(calls)[0] == "https://linkedin.com/in/jane"


# ── Outreach ─────────────────────────────────────────────────────────────────
def test_record_outreach_links_job_and_contact():
    http, calls = _fake([])
    draft = EmailDraft(job_id="j1", company="DBS", to_email="jane@dbs.com", to_name="Jane",
                       role_type="recruiter", subject="Re: Head of Data", body="Hello")
    key = _repo(http).record_outreach(draft, "dbs|head of data|u1", "jane@dbs.com")
    assert key == "jane@dbs.com|Re: Head of Data"
    row = _appended(calls)
    assert row[3] == "jane@dbs.com"
    assert row[4] == "drafted"
    assert row[6] == "dbs|head of data|u1"  # Job key
    assert row[7] == "jane@dbs.com"          # Contact key


def test_record_outreach_without_links():
    http, calls = _fake([])
    draft = EmailDraft(job_id="j1", company="DBS", to_email="jane@dbs.com", to_name="Jane",
                       role_type="recruiter", subject="Hi", body="Hello")
    _repo(http).record_outreach(draft)
    row = _appended(calls)
    assert row[6] == "" and row[7] == ""


# ── Bootstrapping ─────────────────────────────────────────────────────────────
def test_ensure_creates_missing_tabs_recolours_and_writes_headers():
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        calls.append((method, url, body))
        if method == "GET" and "/values/" not in url:  # spreadsheet metadata
            return {"sheets": [{"properties": {"title": "Jobs", "sheetId": 0}}]}  # only Jobs
        if method == "GET":  # header / column reads are empty
            return {"values": []}
        return {}

    repo = GoogleSheetsRepository("sheet123", token="tok", http=http)
    repo.upsert_job(_job())

    batch = [c for c in calls if c[0] == "POST" and ":batchUpdate" in c[1]][0]
    reqs = batch[2]["requests"]
    added = {r["addSheet"]["properties"]["title"] for r in reqs if "addSheet" in r}
    assert added == {"Contacts", "Outreach", "Networking Tracker"}  # Jobs already exists
    # Jobs (pre-existing) is recoloured, not re-added.
    recolour = [r for r in reqs if "updateSheetProperties" in r]
    assert recolour[0]["updateSheetProperties"]["properties"]["sheetId"] == 0
    # New tabs carry their colour: Networking Tracker orange, application tabs green.
    net = next(r for r in reqs if r.get("addSheet", {}).get("properties", {}).get("title")
               == "Networking Tracker")
    assert net["addSheet"]["properties"]["tabColor"]["red"] > 0.9  # orange
    # Header rows written for all four tabs (PUT to row 1).
    header_puts = [c for c in calls if c[0] == "PUT" and "%211%3A1" not in c[1] and "A1" in c[1]]
    assert len(header_puts) >= 4


def test_upsert_networking_keyed_by_email():
    http, calls = _fake([])
    key = _repo(http).upsert_networking(
        "Sam Lee", email="sam@acme.com", company="Acme", source="gmail",
        last_contacted="2026-06-20",
    )
    assert key == "sam@acme.com"
    row = _appended(calls)
    assert row == ["sam@acme.com", "Sam Lee", "sam@acme.com", "Acme", "", "",
                   "gmail", "2026-06-20", "new", ""]


def test_upsert_networking_falls_back_to_name():
    http, calls = _fake([])
    key = _repo(http).upsert_networking("No Email Person")
    assert key == "No Email Person"
    assert _appended(calls)[0] == "No Email Person"


# ── Backup ────────────────────────────────────────────────────────────────────
def test_snapshot_to_creates_dated_tabs_and_writes_values():
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        calls.append((method, url, body))
        if method == "GET" and "backup999" in url and "/values/" not in url:
            return {"sheets": []}  # backup spreadsheet starts empty
        if method == "GET" and "A1%3AZZ" in url:
            return {"values": [["DedupeKey", "Title"], ["k1", "Head of Data"]]}
        return {}

    repo = _repo(http)
    written = repo.snapshot_to("backup999", suffix="2026-06-21")
    assert written == ["Jobs 2026-06-21", "Contacts 2026-06-21",
                       "Outreach 2026-06-21", "Networking Tracker 2026-06-21"]
    # Each snapshot tab is created in the backup spreadsheet then filled with source values.
    adds = [c for c in calls if c[0] == "POST" and "backup999" in c[1] and ":batchUpdate" in c[1]]
    assert len(adds) == 4
    puts = [c for c in calls if c[0] == "PUT" and "backup999" in c[1]]
    assert puts[0][2]["values"][1] == ["k1", "Head of Data"]
