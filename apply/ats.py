"""Hosted application-form plans.

These adapters do not call employer-owned Greenhouse/Lever APIs. Those APIs require
credentials belonging to the employer. Applicant automation must fill the public hosted
form in a browser and retain job-specific questions for human review.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from models import Applicant, Job


@dataclass(frozen=True)
class ApplicationPlan:
    """Represent application plan."""
    provider: str
    form_url: str
    fields: dict[str, str]
    resume_path: str = ""
    resume_sha256: str = ""


def _split_name(name: str) -> tuple[str, str]:
    """Split name."""
    parts = (name or "").split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last


def _hosted_form_url(job: Job) -> str:
    """Hosted form url."""
    url = job.url.strip()
    if (job.ats_type or "").casefold() == "greenhouse" and "#" not in url:
        return f"{url}#app"
    return url


def hosted_application_plan(job: Job, applicant: Applicant) -> ApplicationPlan:
    """Hosted application plan."""
    first, last = _split_name(applicant.name)
    # Custom answers are loaded first so they can never replace verified identity fields.
    fields = {
        **applicant.answers,
        "first_name": first,
        "last_name": last,
        "name": applicant.name,
        "email": applicant.email,
        "phone": applicant.phone,
        "linkedin": applicant.linkedin_url,
        "github": applicant.github_url,
        "location": applicant.location,
        "current_company": applicant.current_company,
        "work_authorization": applicant.work_authorization,
        "sponsorship_required": applicant.sponsorship_required,
        "notice_period": applicant.notice_period,
        "salary_expectation": applicant.salary_expectation,
    }
    return ApplicationPlan(
        provider=(job.ats_type or urlparse(job.url).netloc or "hosted_form").casefold(),
        form_url=_hosted_form_url(job),
        fields={key: value for key, value in fields.items() if value},
        resume_path=applicant.resume_path,
    )


ADAPTERS = {
    provider: hosted_application_plan
    for provider in (
        "greenhouse", "lever", "workday", "linkedin", "mycareersfuture",
        "efinancialcareers",
    )
}
