from __future__ import annotations

from models import Contact, Job
from network.outreach import build_drafts


def _objects() -> tuple[Job, Contact, Contact]:
    job = Job(
        id="j1",
        source="test",
        company_canonical="Acme",
        dedupe_key="acme|backend engineer",
        title="Backend Engineer",
        url="https://acme.com/jobs/1",
    )
    recruiter = Contact(
        id="r@acme.com", name="Jane Doe", company_canonical="Acme",
        role="Technical Recruiter", role_type="recruiter", email="r@acme.com", confidence=90,
    )
    manager = Contact(
        id="m@acme.com", name="Sam Lee", company_canonical="Acme",
        role="Engineering Manager", role_type="hiring_manager", email="m@acme.com", confidence=80,
    )
    return job, recruiter, manager


def test_build_drafts_returns_two():
    job, recruiter, manager = _objects()
    assert len(build_drafts(job, [recruiter, manager], "Alice", "I love Rust.")) == 2


def test_subjects_differ_by_role_type():
    job, recruiter, manager = _objects()
    drafts = build_drafts(job, [recruiter, manager], "Alice")
    r = next(d for d in drafts if d.role_type == "recruiter")
    m = next(d for d in drafts if d.role_type == "hiring_manager")
    assert r.subject != m.subject


def test_bodies_contain_title_and_first_name():
    job, recruiter, manager = _objects()
    drafts = build_drafts(job, [recruiter, manager], "Alice")
    for d in drafts:
        assert "Backend Engineer" in d.body
    assert "Jane" in next(d for d in drafts if d.role_type == "recruiter").body
    assert "Sam" in next(d for d in drafts if d.role_type == "hiring_manager").body


def test_empty_email_skipped():
    job, _, manager = _objects()
    ghost = Contact(id="g", name="Ghost", company_canonical="Acme", role_type="recruiter", email="")
    drafts = build_drafts(job, [ghost, manager], "Alice")
    assert len(drafts) == 1
    assert drafts[0].to_email == "m@acme.com"
