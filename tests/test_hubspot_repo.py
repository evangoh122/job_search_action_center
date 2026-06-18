from __future__ import annotations

from typing import Any

from models import Job
from store.hubspot_repo import HubSpotRepository
from store.repository import SqliteRepository


def _fake_http_factory():
    """Return (http_fn, recorded_calls). Calls to .../search return {"results": search_result}
    (a mutable list the test can set); every other call returns {"id": "deal-1"}."""
    recorded: list[tuple[str, str, dict | None]] = []
    search_result: list[dict[str, Any]] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        recorded.append((method, url, body))
        if url.endswith("/search"):
            return {"results": search_result}
        return {"id": "deal-1"}

    http.search_result = search_result  # type: ignore[attr-defined]
    return http, recorded


def _make_job(**overrides: Any) -> Job:
    defaults = dict(
        id="job-001",
        source="test",
        company_canonical="Acme Corp",
        dedupe_key="dedupe-001",
        title="Senior Engineer",
        url="https://example.com/job/001",
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def test_upsert_creates_when_absent():
    http, recorded = _fake_http_factory()
    HubSpotRepository(token="tok", http=http).upsert_job(_make_job())
    method, url, body = recorded[1]
    assert method == "POST"
    assert url.endswith("/crm/v3/objects/deals")
    assert "properties" in (body or {})


def test_upsert_updates_when_present():
    http, recorded = _fake_http_factory()
    http.search_result.append({"id": "99"})  # type: ignore[attr-defined]
    HubSpotRepository(token="tok", http=http).upsert_job(_make_job())
    method, url, _ = recorded[1]
    assert method == "PATCH"
    assert "/deals/99" in url


def test_get_job_roundtrip():
    job = _make_job()
    http, _ = _fake_http_factory()
    http.search_result.append(  # type: ignore[attr-defined]
        {"id": "1", "properties": {"job_data": job.model_dump_json()}}
    )
    result = HubSpotRepository(token="tok", http=http).get_job(job.id)
    assert result is not None
    assert result.title == job.title
    assert result.dedupe_key == job.dedupe_key


def test_list_jobs_paginates():
    job_a = _make_job(id="a", dedupe_key="a")
    job_b = _make_job(id="b", dedupe_key="b")
    pages = [
        {
            "results": [{"properties": {"job_data": job_a.model_dump_json()}}],
            "paging": {"next": {"after": "CURSOR"}},
        },
        {"results": [{"properties": {"job_data": job_b.model_dump_json()}}]},
    ]
    calls: list[str] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        calls.append(url)
        return pages[len(calls) - 1]

    jobs = HubSpotRepository(token="tok", http=http).list_jobs()
    assert {j.id for j in jobs} == {"a", "b"}
    assert "after=CURSOR" in calls[1]  # second page followed the cursor


def test_counter_delegates():
    http, _ = _fake_http_factory()
    repo = HubSpotRepository(token="tok", http=http, counter=SqliteRepository(":memory:"))
    repo.incr_action("apply", "d")
    repo.incr_action("apply", "d")
    assert repo.count_actions("apply", "d") == 2
