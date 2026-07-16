from __future__ import annotations

import json
from datetime import datetime, timedelta

from sources.efinancialcareers import EFinancialCareersSource


_RECENT = (datetime.now() - timedelta(days=1)).date().isoformat()
_OLD = (datetime.now() - timedelta(days=60)).date().isoformat()


def _html_with_json_ld() -> str:
    jobs = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "JobPosting",
                "title": "VP, Data Analytics",
                "hiringOrganization": {"name": "DBS"},
                "url": "/jobs-Singapore-VP-Data-Analytics.id1",
                "datePosted": _RECENT,
                "jobLocation": {"address": {"addressLocality": "Singapore"}},
                "description": "<p>Lead &amp; build analytics teams</p>",
            },
            {
                "@type": "JobPosting",
                "title": "Finance Operations Associate",
                "hiringOrganization": {"name": "Acme"},
                "url": "/jobs-Singapore-Ops.id2",
                "datePosted": _RECENT,
                "jobLocation": {"address": {"addressLocality": "Singapore"}},
            },
            {
                "@type": "JobPosting",
                "title": "Head of Data",
                "hiringOrganization": {"name": "Old Bank"},
                "url": "/jobs-Singapore-Head-Data.id3",
                "datePosted": _OLD,
                "jobLocation": {"address": {"addressLocality": "Singapore"}},
            },
        ],
    }
    return f'<html><script type="application/ld+json">{json.dumps(jobs)}</script></html>'


def test_fetch_maps_json_ld_jobs_and_filters_title_and_age() -> None:
    source = EFinancialCareersSource(["data"], http_get=lambda url: _html_with_json_ld())
    jobs = source.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "efinancialcareers"
    assert job.company == "DBS"
    assert job.title == "VP, Data Analytics"
    assert job.url == "https://www.efinancialcareers.sg/jobs-Singapore-VP-Data-Analytics.id1"
    assert job.ats_type == "efinancialcareers"
    assert job.posted_at is not None and job.posted_at.tzinfo is None
    assert job.description == "Lead & build analytics teams"


def test_fetch_parses_embedded_app_json_and_dedupes_across_terms() -> None:
    payload = {
        "props": {
            "pageProps": {
                "jobs": [
                    {
                        "title": "Data Science Lead",
                        "companyName": "Standard Chartered",
                        "jobUrl": "https://www.efinancialcareers.sg/jobs-Singapore-Data-Science-Lead.id4",
                        "postedDate": _RECENT,
                        "location": "Singapore",
                        "summary": "ML platform role",
                    }
                ]
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    calls: list[str] = []

    def fake_get(url: str) -> str:
        calls.append(url)
        return html

    source = EFinancialCareersSource(["data", "analytics"], http_get=fake_get)
    jobs = source.fetch()

    assert len(calls) == 2
    assert len(jobs) == 1
    assert jobs[0].company == "Standard Chartered"
    assert jobs[0].description == "ML platform role"


def test_location_filter() -> None:
    payload = {
        "@type": "JobPosting",
        "title": "Data Scientist",
        "hiringOrganization": {"name": "Global Bank"},
        "url": "/jobs-London-Data-Scientist.id5",
        "datePosted": _RECENT,
        "jobLocation": {"address": {"addressLocality": "London"}},
    }
    html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'

    source = EFinancialCareersSource(["data"], location="Singapore", http_get=lambda url: html)

    assert source.fetch() == []


def test_location_filter_rejects_missing_location() -> None:
    payload = {
        "@type": "JobPosting", "title": "Data Scientist",
        "hiringOrganization": {"name": "Global Bank"},
        "url": "/jobs-Data-Scientist.id6", "datePosted": _RECENT,
    }
    html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'
    source = EFinancialCareersSource(["data"], location="Singapore", http_get=lambda url: html)
    assert source.fetch() == []


def test_failed_fetch_is_skipped() -> None:
    def boom(url: str) -> str:
        raise RuntimeError("blocked")

    source = EFinancialCareersSource(["data"], http_get=boom)

    assert source.fetch() == []


def test_uses_current_slug_search_url() -> None:
    calls: list[str] = []
    source = EFinancialCareersSource(
        ["Data Analytics"],
        location="Singapore",
        http_get=lambda url: calls.append(url) or "<html></html>",
    )
    source.fetch()
    assert calls == [
        "https://www.efinancialcareers.sg/jobs/data-analytics/in-singapore"
    ]
