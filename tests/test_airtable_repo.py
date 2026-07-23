from __future__ import annotations

from datetime import datetime

from models import Contact, EmailDraft, Job
from store.airtable_repo import AirtableRepository


def _job() -> Job:
    """Provide a test helper for job."""
    return Job(
        id="j1", source="mycareersfuture", company_canonical="DBS",
        dedupe_key="dbs|head of data|u1", title="Head of Data",
        url="https://x/1", description="machine learning Databricks",
        score=88.0, tier="B", posted_at=datetime(2026, 6, 19),
    )


def _fake_http(search_result: list):
    """Provide a test helper for fake http."""
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
        calls.append((method, url, body))
        if method == "GET":
            return {"records": search_result}
        return {"records": [{"id": "rec123"}]}

    return http, calls


def test_creates_when_absent():
    """Verify creating when absent."""
    http, calls = _fake_http([])
    rid = AirtableRepository("tok", "appX", http=http).upsert_job(_job())
    assert rid == "rec123"
    post = [c for c in calls if c[0] == "POST"][0]
    fields = post[2]["records"][0]["fields"]
    assert fields["Title"] == "Head of Data"
    assert fields["Tier"] == "B"
    assert fields["Posted"] == "2026-06-19"
    assert fields["DedupeKey"] == "dbs|head of data|u1"


def test_updates_when_present():
    """Verify updating when present."""
    http, calls = _fake_http([{"id": "recOLD"}])
    rid = AirtableRepository("tok", "appX", http=http).upsert_job(_job())
    assert rid == "recOLD"
    assert any(c[0] == "PATCH" for c in calls)


def test_tier_none_omitted():
    """Verify the tier none omitted scenario."""
    job = _job()
    job.tier = None
    http, calls = _fake_http([])
    AirtableRepository("tok", "appX", http=http).upsert_job(job)
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert "Tier" not in fields  # singleSelect rejects empty


def _contact(**kw) -> Contact:
    """Provide a test helper for contact."""
    base = dict(id="c1", name="Jane Tan", company_canonical="DBS", role="Talent Acquisition",
                role_type="recruiter", email="jane@dbs.com", confidence=92)
    base.update(kw)
    return Contact(**base)


def test_upsert_contact_creates():
    """Verify the upsert contact creates scenario."""
    http, calls = _fake_http([])
    rid = AirtableRepository("tok", "appX", http=http).upsert_contact(_contact())
    assert rid == "rec123"
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert fields["Email"] == "jane@dbs.com"
    assert fields["Type"] == "recruiter"
    assert fields["Confidence"] == 92
    # deduped by Email
    get = [c for c in calls if c[0] == "GET"][0]
    assert "Email" in get[1]


def test_upsert_contact_invalid_type_omitted():
    """Verify the upsert contact invalid type omitted scenario."""
    http, calls = _fake_http([])
    AirtableRepository("tok", "appX", http=http).upsert_contact(_contact(role_type=""))
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert "Type" not in fields  # singleSelect rejects unknown values


def test_upsert_contact_dedupes_by_linkedin_when_no_email():
    """Verify the upsert contact dedupes by linkedin when no email scenario."""
    http, calls = _fake_http([])
    c = _contact(email="", linkedin_url="https://linkedin.com/in/jane")
    AirtableRepository("tok", "appX", http=http).upsert_contact(c)
    get = [c for c in calls if c[0] == "GET"][0]
    assert "LinkedIn" in get[1]


def test_record_outreach_links_job_and_contact():
    """Verify the record outreach links job and contact scenario."""
    http, calls = _fake_http([])
    draft = EmailDraft(job_id="j1", company="DBS", to_email="jane@dbs.com", to_name="Jane",
                       role_type="recruiter", subject="Re: Head of Data", body="Hello")
    rid = AirtableRepository("tok", "appX", http=http).record_outreach(draft, "recJOB", "recCON")
    assert rid == "rec123"
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert fields["Job"] == ["recJOB"]
    assert fields["Contact"] == ["recCON"]
    assert fields["To"] == "jane@dbs.com"
    assert fields["Status"] == "drafted"


def test_record_outreach_without_links():
    """Verify the record outreach without links scenario."""
    http, calls = _fake_http([])
    draft = EmailDraft(job_id="j1", company="DBS", to_email="jane@dbs.com", to_name="Jane",
                       role_type="recruiter", subject="Hi", body="Hello")
    AirtableRepository("tok", "appX", http=http).record_outreach(draft)
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert "Job" not in fields and "Contact" not in fields
