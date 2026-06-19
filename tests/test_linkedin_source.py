from __future__ import annotations

from datetime import datetime, timedelta

from models import RawJob
from sources.linkedin import LinkedInJobSource


def _today_iso() -> str:
    return datetime.now().isoformat()


def _old_iso() -> str:
    return (datetime.now() - timedelta(days=5)).isoformat()


def _source(items: list[dict], terms: list[str] | None = None) -> LinkedInJobSource:
    def fake_post(url: str, body: dict) -> list:
        return items

    return LinkedInJobSource("tok", terms or ["head of data"], http_post=fake_post)


def test_returns_raw_jobs():
    items = [{"jobUrl": "https://li.co/j/1", "companyName": "DBS", "title": "Head of Data",
               "postedAt": _today_iso(), "descriptionText": "Lead ML teams"}]
    jobs = _source(items).fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert isinstance(j, RawJob)
    assert j.source == "linkedin"
    assert j.company == "DBS"
    assert j.title == "Head of Data"
    assert j.description == "Lead ML teams"
    assert j.ats_type == "linkedin"


def test_filters_old_jobs():
    items = [
        {"jobUrl": "https://li.co/j/new", "companyName": "DBS", "title": "VP Data",
         "postedAt": _today_iso()},
        {"jobUrl": "https://li.co/j/old", "companyName": "DBS", "title": "Analyst",
         "postedAt": _old_iso()},
    ]
    jobs = _source(items).fetch()
    assert len(jobs) == 1
    assert "new" in jobs[0].url


def test_dedupes_across_terms():
    item = {"jobUrl": "https://li.co/j/shared", "companyName": "OCBC", "title": "Head of Analytics",
            "postedAt": _today_iso()}
    calls = []

    def fake_post(url: str, body: dict) -> list:
        calls.append(body["title"])  # actor's keyword field is `title`
        return [item]

    src = LinkedInJobSource("tok", ["term1", "term2"], http_post=fake_post)
    jobs = src.fetch()
    assert len(calls) == 2
    assert len(jobs) == 1  # same URL deduped


def test_skips_missing_company_or_title():
    items = [
        {"jobUrl": "https://li.co/j/1", "companyName": "", "title": "VP", "postedAt": _today_iso()},
        {"jobUrl": "https://li.co/j/2", "companyName": "DBS", "title": "", "postedAt": _today_iso()},
        {"jobUrl": "https://li.co/j/3", "companyName": "DBS", "title": "VP Data", "postedAt": _today_iso()},
    ]
    jobs = _source(items).fetch()
    assert len(jobs) == 1
    assert jobs[0].url == "https://li.co/j/3"


def test_tolerates_no_posted_at():
    """Items without a date are included (we can't confirm freshness, but don't exclude)."""
    items = [{"jobUrl": "https://li.co/j/nodates", "companyName": "UOB",
               "title": "Director Analytics"}]
    jobs = _source(items).fetch()
    assert len(jobs) == 1
    assert jobs[0].posted_at is None


def test_sends_correct_actor_schema():
    """24h window must send the actor's native filter: title + publishedAt=r86400 + rows."""
    sent = {}

    def fake_post(url: str, body: dict) -> list:
        sent.update(body)
        return []

    LinkedInJobSource("tok", ["head of data"], location="Singapore",
                      max_age_days=1, max_results_per_term=25, http_post=fake_post).fetch()
    assert sent["title"] == "head of data"
    assert sent["location"] == "Singapore"
    assert sent["rows"] == 25
    assert sent["publishedAt"] == "r86400"  # past 24 hours


def test_parses_publishedat_date_field():
    items = [{"jobUrl": "https://li.co/j/1", "companyName": "OCBC", "title": "Data & AI Architect",
               "publishedAt": datetime.now().date().isoformat()}]
    jobs = _source(items).fetch()
    assert len(jobs) == 1
    assert jobs[0].posted_at is not None


def test_tolerates_apify_failure():
    """A failed Apify call returns empty list without raising."""
    def bad_post(url: str, body: dict) -> list:
        raise RuntimeError("network error")

    src = LinkedInJobSource("tok", ["head of data"], http_post=bad_post)
    jobs = src.fetch()
    assert jobs == []
