import json

import pytest

from models import Contact, Job, LinkedInPostMatch
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


def test_linkedin_post_match_roundtrip():
    repo = SqliteRepository()
    match = LinkedInPostMatch(
        id="j1|p1", job_id="j1", job_key="acme|role", company="Acme",
        job_title="Role", job_url="https://linkedin.com/jobs/view/1",
        post_url="https://linkedin.com/posts/p1", post_text="We are hiring",
        author_name="Jane", confidence=1.0, evidence=["exact_job_url"],
    )
    repo.upsert_linkedin_post_match(match)
    assert repo.list_linkedin_post_matches("j1") == [match]


@pytest.mark.parametrize("statuses", [("new", "applied"), ("applied", "new")])
def test_legacy_key_migration_preserves_strongest_status(tmp_path, statuses):
    db = tmp_path / "jobs.sqlite"
    repo = SqliteRepository(str(db))
    jobs = [
        _job("job-1", "legacy-one").model_copy(update={"status": statuses[0]}),
        _job("job-2", "legacy-two").model_copy(update={"status": statuses[1]}),
    ]
    with repo.conn:
        repo.conn.executemany(
            "INSERT INTO jobs (id, dedupe_key, data) VALUES (?, ?, ?)",
            [(job.id, job.dedupe_key, json.dumps(job.model_dump(mode="json"))) for job in jobs],
        )
    repo.conn.close()

    migrated = SqliteRepository(str(db)).list_jobs()
    assert len(migrated) == 1
    assert migrated[0].status == "applied"
