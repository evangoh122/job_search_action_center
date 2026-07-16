from __future__ import annotations

import pytest

from runner import _workday_location
from sources.workday import DEFAULT_BANK_TENANTS, WorkdaySource


def _fake():
    """Fake Workday CxS: a search returns 3 postings; detail returns a description."""
    posts = {
        "jobPostings": [
            {"title": "VP, Data Science", "externalPath": "/job/Singapore/VP-Data-Science_1",
             "locationsText": "Singapore"},
            {"title": "Office Manager", "externalPath": "/job/Singapore/Office-Manager_2",
             "locationsText": "Singapore"},
            {"title": "Data Engineer", "externalPath": "/job/London/Data-Engineer_3",
             "locationsText": "London, United Kingdom"},
        ]
    }

    def post(url: str, body: dict) -> dict:
        return posts if body.get("searchText") == "data" else {"jobPostings": []}

    def get(url: str) -> dict:
        return {"jobPostingInfo": {"jobDescription": "Lead <b>ML</b> &amp; analytics"}}

    return post, get


def _src(**kw):
    post, get = _fake()
    return WorkdaySource(
        tenants=[{"company": "Citi", "host": "citi.wd5.myworkdayjobs.com",
                  "tenant": "citi", "site": "2"}],
        search_terms=["data"], http_post=post, http_get=get, **kw,
    )


def test_filters_by_title_keyword():
    titles = {j.title for j in _src().fetch()}
    assert "VP, Data Science" in titles
    assert "Office Manager" not in titles  # no data/AI keyword


def test_location_filter():
    titles = {j.title for j in _src(location_contains="Singapore").fetch()}
    assert "Data Engineer" not in titles  # London filtered out
    assert "VP, Data Science" in titles


def test_maps_fields_url_and_description():
    job = next(j for j in _src().fetch() if j.title == "VP, Data Science")
    assert job.source == "workday"
    assert job.company == "Citi"
    assert job.ats_type == "workday"
    assert job.url == "https://citi.wd5.myworkdayjobs.com/2/job/Singapore/VP-Data-Science_1"
    assert job.posted_at is None
    assert job.description == "Lead ML & analytics"  # detail fetched, html stripped


def test_enrich_off_skips_detail_call():
    post, _ = _fake()
    calls = []
    def get(url):  # should never be called when enrich=False
        calls.append(url); return {}
    src = WorkdaySource(tenants=[{"company": "Citi", "host": "h", "tenant": "t", "site": "s"}],
                        search_terms=["data"], http_post=post, http_get=get, enrich=False)
    jobs = src.fetch()
    assert jobs and all(j.description == "" for j in jobs)
    assert calls == []


def test_failed_tenant_is_skipped():
    def boom(url, body):
        raise RuntimeError("422")
    src = WorkdaySource(tenants=[{"company": "X", "host": "h", "tenant": "t", "site": "s"}],
                        search_terms=["data"], http_post=boom, http_get=lambda u: {})
    assert src.fetch() == []


def test_default_tenants_cover_verified_singapore_workday_financial_employers():
    expected = {
        "Citi", "Deutsche Bank", "Morgan Stanley", "DBS", "UOB", "MUFG",
        "Mizuho", "Wells Fargo", "State Street", "Northern Trust", "BlackRock",
    }
    companies = {tenant["company"] for tenant in DEFAULT_BANK_TENANTS}
    assert companies == expected
    assert len({tenant["host"] for tenant in DEFAULT_BANK_TENANTS}) == len(expected)


@pytest.mark.parametrize("configured", [None, "", "London", "Singapore"])
def test_runner_enforces_singapore_workday_location(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("WORKDAY_LOCATION", raising=False)
    else:
        monkeypatch.setenv("WORKDAY_LOCATION", configured)
    assert _workday_location() == "Singapore"
