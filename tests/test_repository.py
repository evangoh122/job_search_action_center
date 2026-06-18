from models import Contact, Job
from store.repository import SqliteRepository


def _job(job_id: str, dedupe_key: str) -> Job:
    return Job(
        id=job_id,
        source="test",
        company_canonical="Acme",
        dedupe_key=dedupe_key,
        title="Data Scientist",
        url="https://example.com/1",
    )


def test_upsert_and_get_roundtrip():
    repo = SqliteRepository()
    repo.upsert_job(_job("job-1", "acme|data scientist|u1"))
    got = repo.get_job("job-1")
    assert got is not None
    assert got.company_canonical == "Acme"
    assert got.title == "Data Scientist"


def test_dedupe_same_key():
    repo = SqliteRepository()
    repo.upsert_job(_job("job-1", "acme|ds|u1"))
    repo.upsert_job(_job("job-2", "acme|ds|u1"))  # same dedupe_key
    assert len(repo.list_jobs()) == 1


def test_upsert_contact():
    repo = SqliteRepository()
    repo.upsert_contact(Contact(id="c1", name="Jane", company_canonical="Acme"))


def test_incr_and_count_actions():
    repo = SqliteRepository()
    assert repo.count_actions("apply", "2026-06-19") == 0
    assert repo.incr_action("apply", "2026-06-19") == 1
    assert repo.incr_action("apply", "2026-06-19") == 2
    assert repo.count_actions("apply", "2026-06-19") == 2
    assert repo.count_actions("apply", "2026-06-20") == 0  # day-scoped
