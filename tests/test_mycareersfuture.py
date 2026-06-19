from __future__ import annotations

from datetime import datetime
from typing import Any

from models import RawJob
from sources.mycareersfuture import MyCareersFutureSource


def test_fetch_filters_old_jobs() -> None:
    today_iso = datetime.now().date().isoformat()
    mock_results: list[dict[str, Any]] = [
        {
            "uuid": "recent-uuid-123",
            "title": "Software Engineer",
            "postedCompany": {"name": "TechCorp SG"},
            "metadata": {"newPostingDate": today_iso},
        },
        {
            "uuid": "old-uuid-999",
            "title": "Legacy Developer",
            "postedCompany": {"name": "OldCorp"},
            "metadata": {"newPostingDate": "2000-01-01"},
        },
    ]

    def fake_http_post(url: str, payload: dict) -> dict:
        assert "mycareersfuture" in url
        return {"results": mock_results}

    source = MyCareersFutureSource(["python"], max_age_days=1, http_post=fake_http_post, enrich=False)
    results = source.fetch()

    assert len(results) == 1
    job = results[0]
    assert isinstance(job, RawJob)
    assert job.company == "TechCorp SG"
    assert "recent-uuid-123" in job.url
    assert job.posted_at is not None


def test_fetch_dedupes_across_terms() -> None:
    today_iso = datetime.now().date().isoformat()
    single = [
        {
            "uuid": "shared-uuid-abc",
            "title": "Full Stack Dev",
            "postedCompany": {"name": "StartupXYZ"},
            "metadata": {"newPostingDate": today_iso},
        }
    ]
    calls = 0

    def fake_http_post(url: str, payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"results": single}

    source = MyCareersFutureSource(["python", "developer"], http_post=fake_http_post, enrich=False)
    results = source.fetch()

    assert calls == 2
    assert len(results) == 1


def test_fetch_enriches_description() -> None:
    today_iso = datetime.now().date().isoformat()
    search = [{"uuid": "u1", "title": "Head of Data", "postedCompany": {"name": "DBS"},
               "metadata": {"newPostingDate": today_iso}}]

    def fake_post(url: str, payload: dict) -> dict:
        return {"results": search}

    def fake_get(url: str) -> dict:
        assert "u1" in url
        return {"description": "<p>Lead <b>machine learning</b> teams</p>",
                "skills": [{"skill": "Databricks"}, {"skill": "PySpark"}]}

    source = MyCareersFutureSource(["data"], http_post=fake_post, enrich=True, http_get=fake_get)
    jobs = source.fetch()
    assert len(jobs) == 1
    desc = jobs[0].description
    assert "machine learning" in desc  # HTML stripped
    assert "Databricks" in desc and "PySpark" in desc  # skills folded in
    assert "<p>" not in desc


def test_fetch_skips_malformed_entries() -> None:
    today_iso = datetime.now().date().isoformat()
    mock_results: list[dict[str, Any]] = [
        {
            "uuid": "good-uuid",
            "title": "Data Analyst",
            "postedCompany": {"name": "DataCo"},
            "metadata": {"newPostingDate": today_iso},
        },
        {"uuid": "bad-uuid"},  # missing fields
    ]

    def fake_http_post(url: str, payload: dict) -> dict:
        return {"results": mock_results}

    source = MyCareersFutureSource(["data"], http_post=fake_http_post, enrich=False)
    results = source.fetch()

    assert len(results) == 1
    assert results[0].company == "DataCo"
