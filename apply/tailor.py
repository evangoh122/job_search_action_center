from __future__ import annotations

from models import ApplicationDraft, Job
from scoring import PRIMARY, SECONDARY  # sets of lowercased keywords


def matched_keywords(job: Job) -> list[str]:
    text = f"{job.title} {job.description}".lower()
    found = [k for k in PRIMARY if k in text] + [k for k in SECONDARY if k in text]
    return sorted(set(found))


def tailor(job: Job, base_summary: str = "", applicant_name: str = "") -> ApplicationDraft:
    kws = matched_keywords(job)
    kw_phrase = ", ".join(kws[:6]) if kws else "the role's core requirements"
    cover_letter = (
        f"Dear Hiring Team at {job.company_canonical},\n\n"
        f"I'm excited to apply for the {job.title} position. {base_summary}\n\n"
        f"My background aligns closely with what you're looking for, "
        f"particularly in {kw_phrase}.\n\n"
        f"I'd welcome the opportunity to discuss how I can contribute.\n\n"
        f"Best regards,\n{applicant_name}"
    )
    return ApplicationDraft(
        job_id=job.id,
        company=job.company_canonical,
        title=job.title,
        url=job.url,
        cover_letter=cover_letter,
        matched_keywords=kws,
    )
