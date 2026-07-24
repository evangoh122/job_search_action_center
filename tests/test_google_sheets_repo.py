from __future__ import annotations

from datetime import datetime

from models import ApplicationDraft, Contact, EmailDraft, Job, LinkedInPostMatch
from store.google_sheets_repo import GoogleSheetsRepository


def _job() -> Job:
    """Provide a test helper for job."""
    return Job(
        id="j1", source="mycareersfuture", company_canonical="DBS",
        dedupe_key="dbs|head of data|u1", title="Head of Data",
        url="https://x/1", description="machine learning Databricks",
        score=88.0, tier="B", posted_at=datetime(2026, 6, 19),
    )


def _repo(http, ready=True) -> GoogleSheetsRepository:
    """Provide a test helper for repo."""
    repo = GoogleSheetsRepository("sheet123", token="tok", http=http)
    repo._ready = ready  # skip tab/header bootstrapping unless a test wants it
    return repo


def _fake(col_a: list | None = None):
    """Fake Sheets HTTP. col_a is the data of the upsert key column (A2:A)."""
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
        calls.append((method, url, body))
        if method == "GET" and "A2%3AA" in url:
            return {"values": col_a or []}
        return {}

    return http, calls


def _appended(calls) -> list:
    """Provide a test helper for appended."""
    post = [c for c in calls if c[0] == "POST" and ":append" in c[1]][0]
    return post[2]["values"][0]


def _updated(calls) -> list:
    """Provide a test helper for updated."""
    put = [c for c in calls if c[0] == "PUT"][0]
    return put[2]["values"][0]


# ── Jobs ─────────────────────────────────────────────────────────────────────
def test_upsert_job_creates_when_absent():
    """Verify the upsert job creates when absent scenario."""
    http, calls = _fake([])
    key = _repo(http).upsert_job(_job())
    assert key == "dbs|head of data|u1"
    row = _appended(calls)
    # Aging (col L) is a live formula, not written by the row upsert -> 11 columns.
    assert row == ["dbs|head of data|u1", "Head of Data", "DBS", "https://x/1",
                   "https://x/1", 88.0, "B", "new", "mycareersfuture", "2026-06-19",
                   "machine learning Databricks"]


def test_refresh_aging_writes_live_formulas():
    # 3 data rows present in column A.
    """Verify the refresh aging writes live formulas scenario."""
    http, calls = _fake([["k1"], ["k2"], ["k3"]])
    repo = _repo(http)
    repo._sheet_ids = {"Jobs": 0}
    n = repo.refresh_aging_formulas()
    assert n == 3
    put = [c for c in calls if c[0] == "PUT" and "USER_ENTERED" in c[1]][0]
    assert "L2%3AL4" in put[1]  # writes L2:L4 (rows 2..4)
    formulas = [v[0] for v in put[2]["values"]]
    assert formulas[0] == '=IF($J2="","",TODAY()-DATEVALUE($J2))'
    assert formulas[2] == '=IF($J4="","",TODAY()-DATEVALUE($J4))'  # row-relative
    # whole-number format applied to column L
    fmt = [c for c in calls if c[0] == "POST" and ":batchUpdate" in c[1]][-1]
    assert fmt[2]["requests"][0]["repeatCell"]["range"]["startColumnIndex"] == 11


def test_upsert_job_updates_when_present():
    """Verify the upsert job updates when present scenario."""
    http, calls = _fake([["dbs|head of data|u1"]])
    key = _repo(http).upsert_job(_job())
    assert key == "dbs|head of data|u1"
    put = [c for c in calls if c[0] == "PUT"][0]
    assert "A2%3AK2" in put[1]  # row 2, columns A..K updated (L/Aging is formula-managed)
    assert not any(":append" in c[1] for c in calls)


def test_tier_none_blank():
    """Verify the tier none blank scenario."""
    job = _job()
    job.tier = None
    http, calls = _fake([])
    _repo(http).upsert_job(job)
    assert _appended(calls)[6] == ""  # Tier column blank, not "None"


def test_salary_range_and_average_are_written_after_existing_applied_column():
    """Verify the salary range and average are written after existing applied column scenario."""
    job = _job()
    job.salary_min = 9000
    job.salary_max = 13000
    job.salary_average = 11000
    job.salary_currency = "SGD"
    job.salary_period = "MONTH"
    http, calls = _fake([])
    _repo(http).upsert_job(job)
    salary_put = next(c for c in calls if c[0] == "PUT" and "N2%3AR2" in c[1])
    assert salary_put[2]["values"][0] == [9000, 13000, 11000, "SGD", "MONTH"]


# ── Contacts ─────────────────────────────────────────────────────────────────
def _contact(**kw) -> Contact:
    """Provide a test helper for contact."""
    base = dict(id="c1", name="Jane Tan", company_canonical="DBS", role="Talent Acquisition",
                role_type="recruiter", email="jane@dbs.com", confidence=92)
    base.update(kw)
    return Contact(**base)


def test_upsert_contact_creates_keyed_by_email():
    """Verify the upsert contact creates keyed by email scenario."""
    http, calls = _fake([])
    key = _repo(http).upsert_contact(_contact())
    assert key == "jane@dbs.com"
    row = _appended(calls)
    assert row[0] == "jane@dbs.com"
    assert row[2] == "jane@dbs.com"
    assert row[5] == "recruiter"
    assert row[7] == 92


def test_upsert_contact_invalid_type_blank():
    """Verify the upsert contact invalid type blank scenario."""
    http, calls = _fake([])
    _repo(http).upsert_contact(_contact(role_type="boss"))
    assert _appended(calls)[5] == ""  # only recruiter|hiring_manager kept


def test_upsert_contact_keys_by_linkedin_when_no_email():
    """Verify the upsert contact keys by linkedin when no email scenario."""
    http, calls = _fake([])
    key = _repo(http).upsert_contact(
        _contact(email="", linkedin_url="https://linkedin.com/in/jane")
    )
    assert key == "https://linkedin.com/in/jane"
    assert _appended(calls)[0] == "https://linkedin.com/in/jane"


# ── Outreach ─────────────────────────────────────────────────────────────────
def test_record_outreach_links_job_and_contact():
    """Verify the record outreach links job and contact scenario."""
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
    """Verify the record outreach without links scenario."""
    http, calls = _fake([])
    draft = EmailDraft(job_id="j1", company="DBS", to_email="jane@dbs.com", to_name="Jane",
                       role_type="recruiter", subject="Hi", body="Hello")
    _repo(http).record_outreach(draft)
    row = _appended(calls)
    assert row[6] == "" and row[7] == ""


# ── Bootstrapping ─────────────────────────────────────────────────────────────
def test_ensure_creates_missing_tabs_recolours_and_writes_headers():
    """Verify the ensure creates missing tabs recolours and writes headers scenario."""
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
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
    assert added == {"Contacts", "Outreach", "Networking Tracker", "Applications",
                     "LinkedIn Post Matches"}
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


def test_ensure_inserts_application_link_column_before_rewriting_legacy_headers():
    """Verify the ensure inserts application link column before rewriting legacy headers scenario.
    """
    calls: list[tuple[str, str, dict | None]] = []
    legacy = ["DedupeKey", "Title", "Company", "URL", "Score", "Tier", "Status",
              "Source", "Posted", "Description", "Aging", "Applied"]

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
        calls.append((method, url, body))
        if method == "GET" and "/values/" not in url:
            return {"sheets": [{"properties": {"title": "Jobs", "sheetId": 7}}]}
        if method == "GET" and "Jobs" in url:
            return {"values": [legacy.copy()]}
        if method == "GET":
            return {"values": []}
        return {}

    GoogleSheetsRepository("sheet123", token="tok", http=http)._ensure_ready()

    insert = next(
        request["insertDimension"]
        for call in calls if call[0] == "POST" and call[2]
        for request in call[2].get("requests", []) if "insertDimension" in request
    )
    assert insert["range"] == {
        "sheetId": 7, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5,
    }


def test_upsert_networking_keyed_by_email():
    """Verify the upsert networking keyed by email scenario."""
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
    """Verify the upsert networking falls back to name scenario."""
    http, calls = _fake([])
    key = _repo(http).upsert_networking("No Email Person")
    assert key == "No Email Person"
    assert _appended(calls)[0] == "No Email Person"


def test_upsert_application_writes_cover_letter_section():
    """Verify the upsert application writes cover letter section scenario."""
    http, calls = _fake([])
    draft = ApplicationDraft(
        job_id="j1", company="DBS", title="Head of Data", url="https://x/1",
        application_link="https://x/1", resume_filename="Evan_Resume.docx",
        cover_letter="Dear DBS, tailored evidence.", matched_keywords=["data governance"],
    )
    assert _repo(http).upsert_application(draft) == "j1"
    row = _appended(calls)
    assert row[0:4] == ["j1", "j1", "DBS", "Head of Data"]
    assert row[6] == "Dear DBS, tailored evidence."
    assert row[7] == "data governance"


def test_upsert_application_rejects_missing_cover_letter():
    """Verify the upsert application rejects missing cover letter scenario."""
    http, _ = _fake([])
    draft = ApplicationDraft(job_id="j1", company="DBS", title="Role", url="https://x",
                             cover_letter="")
    import pytest
    with pytest.raises(ValueError, match="requires a cover letter"):
        _repo(http).upsert_application(draft)


def test_upsert_linkedin_post_match_writes_evidence_and_review_status():
    """Verify the upsert linkedin post match writes evidence and review status scenario."""
    http, calls = _fake([])
    match = LinkedInPostMatch(
        id="j1|p1", job_id="j1", job_key="dbs|head of data", company="DBS",
        job_title="Head of Data", job_url="https://linkedin.com/jobs/view/123456",
        post_url="https://linkedin.com/posts/p1", post_text="We are hiring",
        author_name="Jane", author_title="Recruiter at DBS",
        author_profile_url="https://linkedin.com/in/jane", author_role_type="recruiter",
        confidence=1.0, evidence=["exact_linkedin_job_id"],
    )
    assert _repo(http).upsert_linkedin_post_match(match) == "j1|p1"
    row = _appended(calls)
    assert row[5] == "https://linkedin.com/posts/p1"
    assert row[11] == 1.0
    assert row[12] == "exact_linkedin_job_id"
    assert row[13] == "hiring"
    assert row[15] == "review_required"


# ── Backup ────────────────────────────────────────────────────────────────────
def test_snapshot_to_creates_dated_tabs_and_writes_values():
    """Verify the snapshot to creates dated tabs and writes values scenario."""
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
        calls.append((method, url, body))
        if method == "GET" and "backup999" in url and "/values/" not in url:
            return {"sheets": []}  # backup spreadsheet starts empty
        if method == "GET" and "A1%3AZZ" in url:
            return {"values": [["DedupeKey", "Title"], ["k1", "Head of Data"]]}
        return {}

    repo = _repo(http)
    written = repo.snapshot_to("backup999", suffix="2026-06-21")
    assert written == ["Jobs 2026-06-21", "Contacts 2026-06-21",
                       "Outreach 2026-06-21", "Networking Tracker 2026-06-21",
                       "Applications 2026-06-21", "LinkedIn Post Matches 2026-06-21"]
    # Each snapshot tab is created in the backup spreadsheet then filled with source values.
    adds = [c for c in calls if c[0] == "POST" and "backup999" in c[1] and ":batchUpdate" in c[1]]
    assert len(adds) == 6
    puts = [c for c in calls if c[0] == "PUT" and "backup999" in c[1]]
    assert puts[0][2]["values"][1] == ["k1", "Head of Data"]
