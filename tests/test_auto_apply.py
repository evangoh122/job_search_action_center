from __future__ import annotations

import json

import pytest

from apply.auto_apply import AutoApplier, load_approval_keys, load_salary_override_keys
from models import Applicant, Job


@pytest.fixture
def applicant(tmp_path) -> Applicant:
    """Provide a test helper for applicant."""
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"resume")
    return Applicant(
        name="Alice Smith",
        email="alice@example.com",
        phone="+11234567890",
        resume_url="https://example.com/alice.pdf",
        resume_path=str(resume),
        linkedin_url="https://linkedin.com/in/alicesmith",
    )


def _job(ats: str, url: str) -> Job:
    """Provide a test helper for job."""
    return Job(
        id="j", source="test", company_canonical="Acme",
        dedupe_key=f"k-{ats}", title="Engineer", url=url, ats_type=ats,
        salary_min=12000, salary_max=14000, salary_currency="SGD", salary_period="MONTH",
    )


class RecordingSubmitter:
    """Group test scenarios for RecordingSubmitter."""
    def __init__(self, result: str = "submitted", exc: Exception | None = None):
        """Provide a test helper for init."""
        self.calls = []
        self.result = result
        self.exc = exc

    def __call__(self, job, applicant, plan):
        """Provide a test helper for call."""
        self.calls.append((job, applicant, plan))
        if self.exc:
            raise self.exc
        return self.result


def test_dry_run_default_prepares_plan_without_submitting(applicant):
    """Verify the dry run default prepares plan without submitting scenario."""
    submitter = RecordingSubmitter()
    applier = AutoApplier(applicant=applicant, submitter=submitter)
    assert applier.apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")) == "dry_run"
    assert applier.last_plan is not None
    assert applier.last_plan.form_url.endswith("#app")
    assert "cover_letter" in applier.last_plan.fields
    assert "Engineer" in applier.last_plan.fields["cover_letter"]
    assert applier.last_draft is not None
    assert submitter.calls == []


def test_live_submission_requires_per_job_approval(applicant):
    """Verify the live submission requires per job approval scenario."""
    submitter = RecordingSubmitter()
    result = AutoApplier(applicant, dry_run=False, submitter=submitter).apply(
        _job("lever", "https://jobs.lever.co/globex/456")
    )
    assert result == "approval_required"
    assert submitter.calls == []


def test_approved_job_uses_browser_submitter(applicant):
    """Verify the approved job uses browser submitter scenario."""
    submitter = RecordingSubmitter()
    result = AutoApplier(
        applicant, dry_run=False, submitter=submitter, approved_job_keys={"k-lever"}
    ).apply(_job("lever", "https://jobs.lever.co/globex/456"))
    assert result == "submitted"
    assert submitter.calls[0][2].fields["email"] == applicant.email
    assert AutoApplier(applicant, approved_job_keys={"k-lever"}).is_approved(
        _job("lever", "https://jobs.lever.co/globex/456")
    )


def test_every_prepared_application_persists_cover_letter_package(applicant):
    """Verify the every prepared application persists cover letter package scenario."""
    saved = []
    applier = AutoApplier(applicant, draft_sink=lambda draft: saved.append(draft) or "draft-1")
    assert applier.apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")) == "dry_run"
    assert len(saved) == 1
    assert saved[0].cover_letter
    assert saved[0].job_id == "j"


def test_supported_hosted_boards_use_review_flow(applicant):
    """Verify the supported hosted boards use review flow scenario."""
    for ats in ("workday", "linkedin", "mycareersfuture", "efinancialcareers"):
        job = _job(ats, f"https://example.com/{ats}")
        result = AutoApplier(
            applicant, dry_run=False, approved_job_keys={job.id}
        ).apply(job)
        assert result == "review_required"


def test_unsupported_ats(applicant):
    """Verify the unsupported ats scenario."""
    assert AutoApplier(applicant, dry_run=False).apply(
        _job("unknown", "https://x/1")
    ) == "unsupported"


def test_incomplete_profile_refuses_live_or_dry_run():
    """Verify the incomplete profile refuses live or dry run scenario."""
    applicant = Applicant(name="Alice", email="")
    assert AutoApplier(applicant).apply(
        _job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")
    ) == "incomplete"


def test_submitter_error_is_isolated(applicant):
    """Verify the submitter error is isolated scenario."""
    submitter = RecordingSubmitter(exc=ConnectionError("timeout"))
    result = AutoApplier(
        applicant, dry_run=False, submitter=submitter, approved_job_keys={"j"}
    ).apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123"))
    assert result == "error"


def test_live_submission_requires_existing_local_resume(applicant):
    """Verify the live submission requires existing local resume scenario."""
    applicant.resume_path = "missing-resume.pdf"
    submitter = RecordingSubmitter()
    result = AutoApplier(
        applicant, dry_run=False, submitter=submitter, approved_job_keys={"j"}
    ).apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123"))
    assert result == "incomplete"
    assert submitter.calls == []


def test_unknown_salary_requires_separate_recorded_override(applicant):
    """Verify the unknown salary requires separate recorded override scenario."""
    job = _job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")
    job.salary_min = job.salary_max = None
    submitter = RecordingSubmitter()
    blocked = AutoApplier(
        applicant, dry_run=False, submitter=submitter, approved_job_keys={job.id}
    )
    assert blocked.apply(job) == "salary_review_required"
    allowed = AutoApplier(
        applicant,
        dry_run=False,
        submitter=submitter,
        approved_job_keys={job.id},
        salary_override_job_keys={job.id},
    )
    assert allowed.apply(job) == "submitted"


def test_custom_answers_cannot_override_verified_identity(applicant):
    """Verify the custom answers cannot override verified identity scenario."""
    applicant.answers = {"email": "attacker@example.com", "phone": "000", "Why us?": "Fit"}
    applier = AutoApplier(applicant)
    assert applier.apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")) == "dry_run"
    assert applier.last_plan.fields["email"] == applicant.email
    assert applier.last_plan.fields["phone"] == applicant.phone
    assert applier.last_plan.fields["Why us?"] == "Fit"


def test_load_approval_keys_accepts_object_or_list(tmp_path):
    """Verify the load approval keys accepts object or list scenario."""
    path = tmp_path / "approvals.json"
    path.write_text(json.dumps({"approved": ["job-1", "key-2"]}), encoding="utf-8")
    assert load_approval_keys(path) == {"job-1", "key-2"}
    path.write_text(json.dumps(["job-3"]), encoding="utf-8")
    assert load_approval_keys(path) == {"job-3"}


def test_load_salary_overrides_only_from_named_field(tmp_path):
    """Verify the load salary overrides only from named field scenario."""
    path = tmp_path / "approvals.json"
    path.write_text(json.dumps({
        "approved": ["job-1"], "salary_overrides": ["job-2"]
    }), encoding="utf-8")
    assert load_salary_override_keys(path) == {"job-2"}
