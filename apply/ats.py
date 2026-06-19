from __future__ import annotations

from models import Applicant, Job


def _split_name(name: str) -> tuple[str, str]:
    parts = (name or "").split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last


def greenhouse_payload(job: Job, a: Applicant) -> tuple[str, dict]:
    first, last = _split_name(a.name)
    return job.url, {
        "first_name": first,
        "last_name": last,
        "email": a.email,
        "phone": a.phone,
        "resume_url": a.resume_url,
    }


def lever_payload(job: Job, a: Applicant) -> tuple[str, dict]:
    return job.url, {
        "name": a.name,
        "email": a.email,
        "phone": a.phone,
        "urls": [u for u in (a.linkedin_url, a.resume_url) if u],
    }


ADAPTERS = {"greenhouse": greenhouse_payload, "lever": lever_payload}
