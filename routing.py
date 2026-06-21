from __future__ import annotations

from config import AUTO_APPLY_THRESHOLD, DRAFT_FLOOR
from models import Job
from scoring import target_priority

# Auto-apply (Tier A) is reserved for top-priority target employers — the SG local banks and
# global investment banks (priority 1). Everything else that clears the floor is a draft (Tier B).
AUTO_APPLY_MAX_PRIORITY = 1

# Sources whose roles are pre-curated enough to treat as Tier A directly (large-fintech
# boards we hand-picked). They still must clear the draft floor to avoid auto-applying noise.
TIER_A_SOURCES = {"greenhouse"}


def apply_tier(job: Job) -> str | None:
    """Track 1 tier:
    A (auto-apply) = a TIER_A_SOURCES role, OR a priority-1 target employer at
                     score >= AUTO_APPLY_THRESHOLD — in both cases score >= DRAFT_FLOOR
    B (draft)      = score >= DRAFT_FLOOR (any company)
    None           = below floor
    """
    if job.score is None:
        return None
    if job.source in TIER_A_SOURCES:  # source-curated boards -> always Tier A
        return "A"
    if job.score < DRAFT_FLOOR:
        return None
    prio = target_priority(job.company_canonical)
    if (
        job.score >= AUTO_APPLY_THRESHOLD
        and prio is not None
        and prio <= AUTO_APPLY_MAX_PRIORITY
    ):
        return "A"
    return "B"


def should_outreach(job: Job) -> bool:
    """Track 2: outreach fires in parallel for any qualified job."""
    return job.score is not None and job.score >= DRAFT_FLOOR
