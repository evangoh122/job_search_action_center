"""Pipeline orchestrator: sources -> normalize -> EXCLUDE -> score -> route -> store.

Phase 0: sources/score/route are stubs. The exclusion gate is real (the one thing
that must work from day one).
"""
from __future__ import annotations

import logging
import uuid

from datetime import datetime, timedelta

from config import DAILY_CAPS
from exclusions import is_excluded_company
from models import Job, RawJob
from network.email_finder import HunterEmailFinder
from network.outreach import build_drafts
from routing import apply_tier, should_outreach
from scoring import final_score
from sources.mycareersfuture import MyCareersFutureSource
from store.repository import Repository, SqliteRepository

logger = logging.getLogger(__name__)

# Small curated default; full role list lives in Target-list.json (Phase 2 will use it).
DEFAULT_TERMS = [
    "data scientist",
    "machine learning engineer",
    "ai engineer",
    "data analyst",
]


def sources() -> list[RawJob]:
    """Live job sources. MyCareersFuture (SG) now; LinkedIn slots in here next."""
    return MyCareersFutureSource(DEFAULT_TERMS, max_age_days=1).fetch()


def normalize(raw: RawJob) -> Job:
    company = raw.company.strip()
    title = raw.title.strip()
    url = raw.url.strip()
    dedupe_key = f"{company.lower()}|{title.lower()}|{url}"
    return Job(
        id=str(uuid.uuid4()),
        source=raw.source,
        company_canonical=company,
        dedupe_key=dedupe_key,
        title=title,
        url=url,
        ats_type=raw.ats_type,
        posted_at=raw.posted_at,
        description=raw.description,
    )


def _within_24h(raw: RawJob) -> bool:
    return raw.posted_at is not None and raw.posted_at >= datetime.now() - timedelta(days=1)


def _run_outreach(job, repo, finder, drafter, applicant_name, day) -> int:
    """Track 2: email recruiter + hiring manager, respecting the daily outreach cap."""
    if finder is None or drafter is None:
        return 0
    contacts = finder.find_people(job.company_canonical, max_each=1)
    drafted = 0
    for draft in build_drafts(job, contacts, applicant_name):
        if repo.count_actions("outreach", day) >= DAILY_CAPS["outreach"]:
            logger.warning("Daily outreach cap reached (%s)", DAILY_CAPS["outreach"])
            break
        drafter.create_draft(draft)
        repo.incr_action("outreach", day)
        drafted += 1
    return drafted


def run(
    repo: Repository | None = None,
    jobs: list[RawJob] | None = None,
    finder=None,
    drafter=None,
    applicant_name: str = "",
) -> dict[str, int]:
    repo = repo or SqliteRepository()
    raws = jobs if jobs is not None else sources()
    day = datetime.now().date().isoformat()
    counts = {"processed": 0, "stored": 0, "excluded": 0, "skipped": 0,
              "qualified": 0, "drafts": 0}
    for raw in raws:
        counts["processed"] += 1
        if not (raw.company or "").strip():
            logger.warning("Skipping job with no company: %s", raw.title)
            counts["skipped"] += 1
            continue
        if is_excluded_company(raw.company):
            counts["excluded"] += 1
            continue
        job = normalize(raw)
        job.score = final_score(job, within_24h=_within_24h(raw))
        job.tier = apply_tier(job)
        repo.upsert_job(job)
        counts["stored"] += 1
        if should_outreach(job):  # Track 2 fires in parallel with applying
            counts["qualified"] += 1
            counts["drafts"] += _run_outreach(job, repo, finder, drafter, applicant_name, day)
    return counts


def _build_outreach_from_env():
    """Enable Track 2 only if a Hunter key exists; Gmail drafts if a Gmail token exists,
    otherwise fall back to the local review-queue JSONL."""
    import os

    hunter = os.environ.get("HUNTER_API_KEY")
    if not hunter:
        logger.info("HUNTER_API_KEY not set — outreach track disabled (apply track still runs).")
        return None, None
    from network.email_finder import HunterEmailFinder
    from network.gmail_drafter import GmailDrafter, ReviewQueueDrafter

    finder = HunterEmailFinder(hunter)
    gmail_token = os.environ.get("GMAIL_TOKEN")
    drafter = GmailDrafter(gmail_token) if gmail_token else ReviewQueueDrafter()
    return finder, drafter


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    import os

    finder, drafter = _build_outreach_from_env()
    result = run(
        finder=finder, drafter=drafter, applicant_name=os.environ.get("APPLICANT_NAME", "")
    )
    print(
        f"processed={result['processed']} stored={result['stored']} "
        f"excluded={result['excluded']} skipped={result['skipped']} "
        f"qualified={result['qualified']} drafts={result['drafts']}"
    )


if __name__ == "__main__":
    main()
