from __future__ import annotations

from config import AUTO_APPLY_THRESHOLD, DRAFT_FLOOR
from models import Job
from scoring import title_on_allowlist

SIMPLE_ATS = {"greenhouse", "lever"}


def apply_tier(job: Job) -> str | None:
    """Track 1: which apply tier (A=auto, B=draft), or None if below floor."""
    if job.score is None:
        return None
    if (
        job.score >= AUTO_APPLY_THRESHOLD
        and job.ats_type in SIMPLE_ATS
        and title_on_allowlist(job)
    ):
        return "A"
    if job.score >= DRAFT_FLOOR:
        return "B"
    return None


def should_outreach(job: Job) -> bool:
    """Track 2: outreach fires in parallel for any qualified job."""
    return job.score is not None and job.score >= DRAFT_FLOOR
