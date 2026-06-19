from __future__ import annotations

from config import AUTO_APPLY_THRESHOLD, DRAFT_FLOOR
from models import Job
from scoring import target_priority

# Auto-apply (Tier A) is reserved for top-priority target employers — the SG local banks and
# global investment banks (priority 1). Everything else that clears the floor is a draft (Tier B).
AUTO_APPLY_MAX_PRIORITY = 1


def apply_tier(job: Job) -> str | None:
    """Track 1 tier, company-driven:
    A (auto-apply) = priority-1 target employer AND score >= AUTO_APPLY_THRESHOLD
    B (draft)      = score >= DRAFT_FLOOR (any company)
    None           = below floor
    """
    if job.score is None:
        return None
    prio = target_priority(job.company_canonical)
    if (
        job.score >= AUTO_APPLY_THRESHOLD
        and prio is not None
        and prio <= AUTO_APPLY_MAX_PRIORITY
    ):
        return "A"
    if job.score >= DRAFT_FLOOR:
        return "B"
    return None


def should_outreach(job: Job) -> bool:
    """Track 2: outreach fires in parallel for any qualified job."""
    return job.score is not None and job.score >= DRAFT_FLOOR
