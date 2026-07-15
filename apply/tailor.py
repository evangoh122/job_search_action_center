from __future__ import annotations

import hashlib

from apply.application_package import resume_filename
from apply.resume_builder import build_resume_variant
from apply.resume_models import ResumeAchievement
from models import ApplicationDraft, Job
from scoring import PRIMARY, SECONDARY  # sets of lowercased keywords


def matched_keywords(job: Job) -> list[str]:
    """Matched keywords."""
    text = f"{job.title} {job.description}".lower()
    found = [k for k in PRIMARY if k in text] + [k for k in SECONDARY if k in text]
    return sorted(set(found))


def _resume_version_id(job: Job, filename: str, evidence_ids: list[str]) -> str:
    """Resume version id."""
    material = "\x1f".join([job.id, job.dedupe_key, filename, *evidence_ids]).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def tailor(
    job: Job,
    base_summary: str = "",
    applicant_name: str = "",
    achievements: list[ResumeAchievement] | None = None,
) -> ApplicationDraft:
    """Tailor."""
    kws = matched_keywords(job)
    kw_phrase = ", ".join(kws[:6]) if kws else "the role's core requirements"
    resume_variant = build_resume_variant(job, achievements or []) if achievements else None
    evidence = ""
    if resume_variant and resume_variant.bullets:
        evidence = "\n\nRelevant evidence includes:\n" + "\n".join(
            f"- {bullet}" for bullet in resume_variant.bullets[:3]
        )
    summary = base_summary.strip() or (
        "My experience is best represented by the evidence in my attached resume; "
        "I have intentionally left out claims that are not supported by it."
    )
    cover_letter = (
        f"Dear Hiring Team at {job.company_canonical},\n\n"
        f"I am applying for the {job.title} position. The role's emphasis on {kw_phrase} "
        f"is closely aligned with the work I want to continue doing.\n\n"
        f"{summary}{evidence}\n\n"
        f"I would welcome a conversation about the outcomes your team needs from this role "
        f"and how my experience could help deliver them.\n\n"
        f"Best regards,\n{applicant_name}"
    )
    filename = resume_filename(job.company_canonical)
    evidence_ids = (
        [item.evidence_id for item in resume_variant.selected_evidence if item.evidence_id]
        if resume_variant
        else []
    )
    return ApplicationDraft(
        job_id=job.id,
        company=job.company_canonical,
        title=job.title,
        url=job.url,
        cover_letter=cover_letter,
        application_link=job.url,
        resume_filename=filename,
        resume_version_id=_resume_version_id(job, filename, evidence_ids),
        resume_evidence_ids=evidence_ids,
        matched_keywords=kws,
        resume_keywords=resume_variant.keywords if resume_variant else [],
        resume_bullets=resume_variant.bullets if resume_variant else [],
        resume_text=resume_variant.text if resume_variant else "",
        resume_fit_brief=(
            resume_variant.fit_brief.model_dump() if resume_variant and resume_variant.fit_brief else {}
        ),
        resume_keyword_map=(
            [item.model_dump() for item in resume_variant.keyword_map] if resume_variant else []
        ),
        resume_selected_evidence=(
            [item.model_dump() for item in resume_variant.selected_evidence] if resume_variant else []
        ),
        resume_evidence_gaps=resume_variant.evidence_gaps if resume_variant else [],
        resume_change_log=resume_variant.change_log if resume_variant else [],
        resume_pagination_status=resume_variant.pagination_status if resume_variant else "",
    )
