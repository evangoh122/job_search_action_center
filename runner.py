"""Pipeline orchestrator: sources -> normalize -> EXCLUDE -> score -> route -> store.

Phase 0: sources/score/route are stubs. The exclusion gate is real (the one thing
that must work from day one).
"""
from __future__ import annotations

import logging
import uuid

from datetime import datetime, timedelta

from exclusions import is_excluded_company
from models import Job, RawJob
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


def run(repo: Repository | None = None, jobs: list[RawJob] | None = None) -> dict[str, int]:
    repo = repo or SqliteRepository()
    raws = jobs if jobs is not None else sources()
    counts = {"processed": 0, "stored": 0, "excluded": 0, "skipped": 0, "outreach": 0}
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
        if should_outreach(job):
            counts["outreach"] += 1
        repo.upsert_job(job)
        counts["stored"] += 1
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run()
    print(
        f"processed={result['processed']} stored={result['stored']} "
        f"excluded={result['excluded']} skipped={result['skipped']} "
        f"outreach={result['outreach']}"
    )


if __name__ == "__main__":
    main()
