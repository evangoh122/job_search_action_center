"""Approval-gated application orchestration.

Dry-run is the default. Live mode additionally requires the vacancy's id or dedupe key in
an approval set and a browser submitter. No applicant-side code calls employer-owned ATS APIs.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Collection
from pathlib import Path

from apply.ats import ADAPTERS, ApplicationPlan
from apply.resume_models import ResumeAchievement
from apply.tailor import tailor
from config import MINIMUM_MONTHLY_SGD
from models import Applicant, ApplicationDraft, Job
from salary import SalaryRange, meets_monthly_sgd_floor

logger = logging.getLogger(__name__)

Submitter = Callable[[Job, Applicant, ApplicationPlan], str]
DraftSink = Callable[[ApplicationDraft], str]


def load_approval_keys(path: str | Path | None) -> set[str]:
    """Load approval keys."""
    if not path:
        return set()
    approval_path = Path(path)
    if not approval_path.exists():
        return set()
    data = json.loads(approval_path.read_text(encoding="utf-8"))
    values = data.get("approved", []) if isinstance(data, dict) else data
    return {str(value) for value in values}


def load_salary_override_keys(path: str | Path | None) -> set[str]:
    """Load explicitly recorded salary-review overrides from an approval file."""
    if not path:
        return set()
    approval_path = Path(path)
    if not approval_path.exists():
        return set()
    data = json.loads(approval_path.read_text(encoding="utf-8"))
    values = data.get("salary_overrides", []) if isinstance(data, dict) else []
    return {str(value) for value in values}


class AutoApplier:
    """Represent auto applier."""
    def __init__(
        self,
        applicant: Applicant,
        dry_run: bool = True,
        submitter: Submitter | None = None,
        approved_job_keys: Collection[str] = (),
        salary_override_job_keys: Collection[str] = (),
        base_summary: str = "",
        draft_sink: DraftSink | None = None,
        achievements: Collection[ResumeAchievement] = (),
    ) -> None:
        """Initialize the instance."""
        self.applicant = applicant
        self.dry_run = dry_run
        self.submitter = submitter
        self.approved_job_keys = set(approved_job_keys)
        self.salary_override_job_keys = set(salary_override_job_keys)
        self.base_summary = base_summary
        self.draft_sink = draft_sink
        self.achievements = list(achievements)
        self.last_plan: ApplicationPlan | None = None
        self.last_draft = None

    def is_approved(self, job: Job) -> bool:
        """Return whether approved."""
        return job.id in self.approved_job_keys or job.dedupe_key in self.approved_job_keys

    def _missing_profile_fields(self) -> list[str]:
        """Missing profile fields."""
        missing = [name for name in ("name", "email", "phone") if not getattr(self.applicant, name)]
        if not (self.applicant.resume_path or self.applicant.resume_url):
            missing.append("resume_path_or_url")
        return missing

    def _salary_is_cleared(self, job: Job) -> bool:
        """Require a conclusive salary floor match or a recorded per-vacancy override."""
        if job.id in self.salary_override_job_keys or job.dedupe_key in self.salary_override_job_keys:
            return True
        salary = SalaryRange(
            job.salary_min,
            job.salary_max,
            job.salary_currency,
            job.salary_period,
        )
        return meets_monthly_sgd_floor(salary, MINIMUM_MONTHLY_SGD)

    def apply(self, job: Job) -> str:
        """Prepare or submit one application while enforcing all live-mode safety gates."""
        builder = ADAPTERS.get((job.ats_type or "").casefold())
        if builder is None:
            logger.info("No hosted-form adapter for %s (%s)", job.ats_type, job.title)
            return "unsupported"
        self.last_plan = builder(job, self.applicant)
        self.last_draft = tailor(
            job,
            self.base_summary,
            self.applicant.name,
            achievements=self.achievements,
        )
        self.last_plan.fields["cover_letter"] = self.last_draft.cover_letter
        if self.draft_sink is not None:
            self.draft_sink(self.last_draft)
        missing = self._missing_profile_fields()
        if missing:
            logger.warning("Application profile incomplete for %s: %s", job.title, ", ".join(missing))
            return "incomplete"
        if self.dry_run:
            logger.info("[DRY_RUN] prepared application for %s at %s", job.title, self.last_plan.form_url)
            return "dry_run"
        if not self.is_approved(job):
            logger.info("Per-job approval required for %s", job.title)
            return "approval_required"
        if self.submitter is None:
            logger.info("Browser submitter not configured for approved job %s", job.title)
            return "review_required"
        resume_path = Path(self.applicant.resume_path) if self.applicant.resume_path else None
        if resume_path is None or not resume_path.is_file():
            logger.warning("A readable local resume file is required for live submission")
            return "incomplete"
        if not self._salary_is_cleared(job):
            logger.warning("Salary review or an explicit per-vacancy override is required")
            return "salary_review_required"
        try:
            result = self.submitter(job, self.applicant, self.last_plan)
            return result if result in {
                "submitted", "submission_unknown", "review_required", "captcha_required"
            } else "error"
        except Exception:
            logger.warning("Browser application failed for %s", job.title, exc_info=True)
            return "error"
