from __future__ import annotations

import json

import pytest

from apply.auto_apply import AutoApplier, load_approval_keys
from models import Applicant, Job


@pytest.fixture
def applicant() -> Applicant:
    return Applicant(
        name="Alice Smith",
        email="alice@example.com",
        phone="+11234567890",
        resume_url="https://example.com/alice.pdf",
        linkedin_url="https://linkedin.com/in/alicesmith",
    )


def _job(ats: str, url: str) -> Job:
    return Job(
        id="j", source="test", company_canonical="Acme",
        dedupe_key=f"k-{ats}", title="Engineer", url=url, ats_type=ats,
    )


class RecordingSubmitter:
    def __init__(self, result: str = "submitted", exc: Exception | None = None):
        self.calls = []
        self.result = result
        self.exc = exc

    def __call__(self, job, applicant, plan):
        self.calls.append((job, applicant, plan))
        if self.exc:
            raise self.exc
        return self.result


def test_dry_run_default_prepares_plan_without_submitting(applicant):
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
    submitter = RecordingSubmitter()
    result = AutoApplier(applicant, dry_run=False, submitter=submitter).apply(
        _job("lever", "https://jobs.lever.co/globex/456")
    )
    assert result == "approval_required"
    assert submitter.calls == []


def test_approved_job_uses_browser_submitter(applicant):
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
    saved = []
    applier = AutoApplier(applicant, draft_sink=lambda draft: saved.append(draft) or "draft-1")
    assert applier.apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")) == "dry_run"
    assert len(saved) == 1
    assert saved[0].cover_letter
    assert saved[0].job_id == "j"


def test_supported_hosted_boards_use_review_flow(applicant):
    for ats in ("workday", "linkedin", "mycareersfuture", "efinancialcareers"):
        job = _job(ats, f"https://example.com/{ats}")
        result = AutoApplier(
            applicant, dry_run=False, approved_job_keys={job.id}
        ).apply(job)
        assert result == "review_required"


def test_unsupported_ats(applicant):
    assert AutoApplier(applicant, dry_run=False).apply(
        _job("unknown", "https://x/1")
    ) == "unsupported"


def test_incomplete_profile_refuses_live_or_dry_run():
    applicant = Applicant(name="Alice", email="")
    assert AutoApplier(applicant).apply(
        _job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")
    ) == "incomplete"


def test_submitter_error_is_isolated(applicant):
    submitter = RecordingSubmitter(exc=ConnectionError("timeout"))
    result = AutoApplier(
        applicant, dry_run=False, submitter=submitter, approved_job_keys={"j"}
    ).apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123"))
    assert result == "error"


def test_load_approval_keys_accepts_object_or_list(tmp_path):
    path = tmp_path / "approvals.json"
    path.write_text(json.dumps({"approved": ["job-1", "key-2"]}), encoding="utf-8")
    assert load_approval_keys(path) == {"job-1", "key-2"}
    path.write_text(json.dumps(["job-3"]), encoding="utf-8")
    assert load_approval_keys(path) == {"job-3"}
