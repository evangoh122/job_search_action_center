from datetime import datetime

from matching import (
    find_description_matches,
    job_identity_key,
    merge_jobs,
    rank_description_matches,
)
from models import Job


def _job(source: str, url: str, *, status: str = "new") -> Job:
    return Job(
        id="stable-id",
        source=source,
        company_canonical="DBS Bank Ltd.",
        dedupe_key=job_identity_key("DBS Bank Ltd.", "Vice President, Data & Analytics"),
        title="Vice President, Data & Analytics",
        url=url,
        posted_at=datetime(2026, 7, 15),
        status=status,
        sources=[source],
        source_urls={source: url},
    )


def test_identity_matches_common_cross_board_variants():
    assert job_identity_key("DBS Bank Ltd.", "Vice President, Data & Analytics") == (
        job_identity_key("DBS Bank", "VP Data and Analytics")
    )


def test_identity_separates_same_title_requisitions_by_stable_url():
    first = job_identity_key("DBS", "VP Data", url="https://dbs.example/jobs/100?utm_source=x")
    same = job_identity_key("DBS", "VP Data", url="https://dbs.example/jobs/100")
    second = job_identity_key("DBS", "VP Data", url="https://dbs.example/jobs/200")
    assert first == same
    assert first != second


def test_merge_retains_links_and_applied_status():
    existing = _job("linkedin", "https://linkedin/jobs/1", status="applied")
    incoming = _job("mycareersfuture", "https://mcf/jobs/2")
    merged = merge_jobs(existing, incoming)
    assert merged.id == "stable-id"
    assert merged.status == "applied"
    assert merged.sources == ["linkedin", "mycareersfuture"]
    assert merged.source_urls == {
        "linkedin": "https://linkedin/jobs/1",
        "mycareersfuture": "https://mcf/jobs/2",
    }


def test_merge_preserves_strongest_status_in_both_orders():
    new = _job("linkedin", "https://linkedin/jobs/1", status="new")
    applied = _job("mycareersfuture", "https://mcf/jobs/2", status="applied")
    assert merge_jobs(new, applied).status == "applied"
    assert merge_jobs(applied, new).status == "applied"


def test_description_starting_with_about_us_retains_substantive_content():
    responsibilities = (
        "About us. We are a bank. Lead the enterprise data platform roadmap, governance, "
        "engineering delivery, cloud controls, analytics products, and regional stakeholders. "
    ) * 4
    left = _job("linkedin", "https://linkedin/jobs/1")
    right = _job("mycareersfuture", "https://mcf/jobs/2")
    left.description = responsibilities
    right.description = responsibilities.replace("regional", "global")
    assert find_description_matches([left, right])


def test_finds_duplicate_from_writeup_when_title_and_company_differ():
    responsibilities = (
        "Lead the enterprise data platform roadmap and manage a regional engineering team. "
        "Own cloud migration, data governance, stakeholder engagement, operating controls, "
        "budget planning, and delivery of analytics products across wholesale banking. "
        "The candidate needs ten years of data leadership, Python, Spark, and AWS experience. "
    ) * 2
    left = _job("linkedin", "https://linkedin/jobs/1")
    left.company_canonical = "Example Bank"
    left.title = "VP, Regional Data Platform"
    left.description = responsibilities
    right = _job("mycareersfuture", "https://mcf/jobs/2")
    right.company_canonical = "Recruitment Agency Pte Ltd"
    right.title = "Data Engineering Leader"
    right.description = responsibilities.replace("stakeholder engagement", "stakeholder management")

    matches = find_description_matches([left, right])
    assert len(matches) == 1
    assert matches[0].description_similarity > 0.9
    assert rank_description_matches([left, right], limit=1)[0] == matches[0]
