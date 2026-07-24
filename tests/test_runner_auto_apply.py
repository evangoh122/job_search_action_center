from models import RawJob
from apply.resume_models import ResumeAchievement
from runner import run
from store.repository import SqliteRepository


class FakeApplier:
    """Group test scenarios for FakeApplier."""
    def __init__(self, approved: bool):
        """Provide a test helper for init."""
        self.dry_run = False
        self.approved = approved
        self.calls = 0

    def is_approved(self, job):
        """Provide a test helper for is approved."""
        return self.approved

    def apply(self, job):
        """Provide a test helper for apply."""
        self.calls += 1
        return "submitted"


class FakeQueue:
    """Group test scenarios for FakeQueue."""
    def __init__(self):
        """Provide a test helper for init."""
        self.items = []

    def add(self, draft):
        """Provide a test helper for add."""
        self.items.append(draft)
        return "draft-id"


def _raw():
    """Provide a test helper for raw."""
    return RawJob(
        source="linkedin", company="Acme", title="Data Platform Lead",
        url="https://example.com/job", ats_type="linkedin",
        description="Lead data engineering and analytics delivery.",
    )


def test_explicitly_approved_tier_b_can_submit(monkeypatch):
    """Verify the explicitly approved tier b can submit scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 60.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "B")
    repo = SqliteRepository()
    applier = FakeApplier(approved=True)
    result = run(repo=repo, jobs=[_raw()], auto_applier=applier)
    assert applier.calls == 1
    assert result["app_drafts"] == 0
    assert repo.list_jobs()[0].status == "applied"


def test_unapproved_tier_b_stays_in_draft_queue(monkeypatch):
    """Verify the unapproved tier b stays in draft queue scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 60.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "B")
    repo = SqliteRepository()
    applier = FakeApplier(approved=False)
    queue = FakeQueue()
    result = run(
        repo=repo, jobs=[_raw()], auto_applier=applier, apply_queue=queue,
        applicant_name="Alice", base_summary="Data leader",
    )
    assert applier.calls == 0
    assert result["app_drafts"] == 1
    assert repo.list_jobs()[0].status == "drafted"


def test_tier_b_draft_uses_structured_achievement_bank(monkeypatch):
    """Verify the tier b draft uses structured achievement bank scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 60.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "B")
    queue = FakeQueue()
    run(
        repo=SqliteRepository(),
        jobs=[_raw()],
        auto_applier=FakeApplier(approved=False),
        apply_queue=queue,
        achievements=[
            ResumeAchievement(
                evidence_id="evidence-1",
                source="master resume",
                keyword="data engineering",
                result="Built analytics pipelines",
                metric="5M rows monthly",
                method="using SQL and governed data workflows",
            )
        ],
    )

    assert queue.items[0].resume_bullets
    assert queue.items[0].resume_selected_evidence[0]["evidence_id"] == "evidence-1"


def test_explicit_approval_can_promote_existing_draft(monkeypatch):
    """Verify the explicit approval can promote existing draft scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 60.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "B")
    repo = SqliteRepository()
    queue = FakeQueue()
    run(
        repo=repo, jobs=[_raw()], auto_applier=FakeApplier(approved=False),
        apply_queue=queue, applicant_name="Alice", base_summary="Data leader",
    )
    assert repo.list_jobs()[0].status == "drafted"

    approved = FakeApplier(approved=True)
    run(repo=repo, jobs=[_raw()], auto_applier=approved)
    assert approved.calls == 1
    assert repo.list_jobs()[0].status == "applied"


def test_salary_floor_prevents_storage_and_application_actions(monkeypatch):
    """Verify the salary floor prevents storage and application actions scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 100.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "A")
    low_salary = _raw().model_copy(update={
        "salary_min": 9000,
        "salary_max": 11999,
        "salary_currency": "SGD",
        "salary_period": "MONTH",
    })
    repo = SqliteRepository()
    applier = FakeApplier(approved=True)

    result = run(repo=repo, jobs=[low_salary], auto_applier=applier)

    assert result["salary_filtered"] == 1
    assert result["stored"] == 0
    assert applier.calls == 0
    assert repo.list_jobs() == []


def test_unknown_salary_remains_eligible(monkeypatch):
    """Verify the unknown salary remains eligible scenario."""
    monkeypatch.setattr("runner.final_score", lambda job, within_24h: 60.0)
    monkeypatch.setattr("runner.apply_tier", lambda job: "C")
    repo = SqliteRepository()

    result = run(repo=repo, jobs=[_raw()])

    assert result["salary_filtered"] == 0
    assert result["stored"] == 1
    assert len(repo.list_jobs()) == 1
