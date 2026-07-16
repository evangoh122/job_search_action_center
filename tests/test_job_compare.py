from job_compare import comparison_markdown, import_application_history, store_listings
from models import RawJob
from store.repository import SqliteRepository


def _raw(source: str, url: str, title: str = "VP Data and Analytics") -> RawJob:
    """Provide a test helper for raw."""
    return RawJob(source=source, company="DBS Bank", title=title, url=url)


def test_store_listings_keeps_same_title_roles_distinct_without_requisition_evidence():
    """Verify the store listings keeps same title roles distinct without requisition evidence
    scenario.
    """
    repo = SqliteRepository()
    added, duplicates = store_listings(repo, [
        _raw("linkedin", "https://li/1"),
        _raw("mycareersfuture", "https://mcf/2", "Vice President Data & Analytics"),
    ])
    assert (added, duplicates) == (2, 0)
    jobs = repo.list_jobs()
    assert len(jobs) == 2
    assert {job.url for job in jobs} == {"https://li/1", "https://mcf/2"}


def test_import_history_marks_report_do_not_apply(tmp_path):
    """Verify the import history marks report do not apply scenario."""
    repo = SqliteRepository()
    store_listings(repo, [_raw("linkedin", "https://li/1")])
    path = tmp_path / "history.csv"
    path.write_text(
        "company,title,status,notes\nDBS Bank,VP Data and Analytics,applied,done\n",
        encoding="utf-8",
    )
    assert import_application_history(repo, path) == (1, 0)
    report = comparison_markdown(repo.list_jobs())
    assert "DO NOT APPLY" in report
    assert "[linkedin](https://li/1)" in report


def test_report_surfaces_writeup_duplicate_candidates():
    """Verify the report surfaces writeup duplicate candidates scenario."""
    repo = SqliteRepository()
    writeup = (
        "Build and lead the data analytics platform. Own architecture, governance, delivery, "
        "cloud migration, senior stakeholder management, and a regional engineering team. "
        "Requires Python, Spark, AWS, banking controls, and ten years of leadership experience. "
    ) * 2
    raws = [
        RawJob(source="linkedin", company="Bank", title="VP Data Platform",
               url="https://li/1", description=writeup),
        RawJob(source="mycareersfuture", company="Recruiter", title="Data Engineering Lead",
               url="https://mcf/2", description=writeup),
    ]
    store_listings(repo, raws)
    report = comparison_markdown(repo.list_jobs())
    assert "Write-up candidates: 1" in report
    assert "Apply once after review" in report


def test_store_listings_auto_merges_similar_title_and_description_with_salary():
    """Verify the store listings auto merges similar title and description with salary scenario."""
    writeup = (
        "Lead the regional governed data platform, architecture, cloud migration, controls, "
        "delivery roadmap, stakeholder management, and an engineering organization. "
        "Requires Python, Spark, AWS, banking controls and ten years of leadership. "
    ) * 3
    repo = SqliteRepository()
    added, duplicates = store_listings(repo, [
        RawJob(source="linkedin", company="DBS", title="VP Regional Data Analytics Platform",
               url="https://li/1", description=writeup,
               salary_min=10000, salary_max=14000, salary_currency="SGD", salary_period="MONTH"),
        RawJob(source="mycareersfuture", company="DBS Bank Ltd",
               title="Vice President, Regional Data Analytics Platform Singapore", url="https://mcf/2",
               description=writeup.replace("roadmap", "programme roadmap"),
               salary_min=9000, salary_max=15000, salary_currency="SGD", salary_period="MONTH"),
    ])
    assert (added, duplicates) == (1, 1)
    job = repo.list_jobs()[0]
    assert set(job.source_urls) == {"linkedin", "mycareersfuture"}
    assert (job.salary_min, job.salary_max, job.salary_average) == (9000, 15000, 12000)
