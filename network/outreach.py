from __future__ import annotations

from models import Contact, EmailDraft, Job


def _first_name(name: str) -> str:
    return (name or "there").split()[0] if name else "there"


def build_draft(
    job: Job,
    contact: Contact,
    applicant_name: str = "",
    highlights: str = "",
) -> EmailDraft:
    fn = _first_name(contact.name)
    parts = [f"Hi {fn},"]

    if contact.role_type == "recruiter":
        subject = f"Application + intro: {job.title}"
        parts.append(
            f"I just applied for the {job.title} role at {job.company_canonical} "
            f"and wanted to introduce myself directly."
        )
        closer = "Would you be open to a quick chat about the role?"
    else:
        subject = f"Re: {job.title} — would love to contribute to your team"
        parts.append(
            f"I applied for the {job.title} role and, as the hiring manager, "
            f"thought I'd reach out directly."
        )
        closer = "I'd welcome the chance to discuss how I could help your team."

    if highlights:
        parts.append(highlights)
    parts.append(closer)
    parts.append(f"Best,\n{applicant_name}")
    body = "\n\n".join(parts)

    return EmailDraft(
        job_id=job.id,
        company=job.company_canonical,
        to_email=contact.email,
        to_name=contact.name,
        role_type=contact.role_type,
        subject=subject,
        body=body,
    )


def build_drafts(
    job: Job,
    contacts: list[Contact],
    applicant_name: str = "",
    highlights: str = "",
) -> list[EmailDraft]:
    return [build_draft(job, c, applicant_name, highlights) for c in contacts if c.email]
