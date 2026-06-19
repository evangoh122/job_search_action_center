from __future__ import annotations

from datetime import datetime

from models import Job
from store.airtable_repo import AirtableRepository


def _job() -> Job:
    return Job(
        id="j1", source="mycareersfuture", company_canonical="DBS",
        dedupe_key="dbs|head of data|u1", title="Head of Data",
        url="https://x/1", description="machine learning Databricks",
        score=88.0, tier="B", posted_at=datetime(2026, 6, 19),
    )


def _fake_http(search_result: list):
    calls: list[tuple[str, str, dict | None]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        calls.append((method, url, body))
        if method == "GET":
            return {"records": search_result}
        return {"records": [{"id": "rec123"}]}

    return http, calls


def test_creates_when_absent():
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
    http, calls = _fake_http([{"id": "recOLD"}])
    rid = AirtableRepository("tok", "appX", http=http).upsert_job(_job())
    assert rid == "recOLD"
    assert any(c[0] == "PATCH" for c in calls)


def test_tier_none_omitted():
    job = _job()
    job.tier = None
    http, calls = _fake_http([])
    AirtableRepository("tok", "appX", http=http).upsert_job(job)
    fields = [c for c in calls if c[0] == "POST"][0][2]["records"][0]["fields"]
    assert "Tier" not in fields  # singleSelect rejects empty
