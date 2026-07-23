from __future__ import annotations

from models import Job
from report import build_report, top_jobs


def _job(score: float | None, title: str, company: str = "Acme") -> Job:
    """Provide a test helper for job."""
    return Job(
        id=f"id-{title}",
        source="test",
        company_canonical=company,
        dedupe_key=f"key-{title}",
        title=title,
        url="https://example.com",
        score=score,
    )


def test_top_jobs_sorted_desc_and_excludes_none():
    """Verify the top jobs sorted desc and excludes none scenario."""
    result = top_jobs([_job(90, "Engineer"), _job(50, "Analyst"), _job(None, "Intern"), _job(80, "Designer")])
    assert [j.title for j in result] == ["Engineer", "Designer", "Analyst"]


def test_top_jobs_respects_n():
    """Verify the top jobs respects n scenario."""
    jobs = [_job(s, f"Job{s}") for s in [90, 80, 50]]
    assert len(top_jobs(jobs, n=2)) == 2
    assert len(top_jobs(jobs, n=0)) == 0


def test_top_jobs_all_none():
    """Verify the top jobs all none scenario."""
    assert top_jobs([_job(None, "A"), _job(None, "B")]) == []


def test_build_report_basic_structure():
    """Verify the build report basic structure scenario."""
    report = build_report({"stored": 3, "applied": 1}, [_job(90, "Engineer"), _job(50, "Analyst")])
    assert "Job Search Action Center" in report
    assert "stored=3" in report
    assert report.index("Engineer") < report.index("Analyst")


def test_build_report_none_scored():
    """Verify the build report none scored scenario."""
    assert "(none scored yet)" in build_report({}, [_job(None, "Intern")])
