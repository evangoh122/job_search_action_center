"""Pipeline orchestrator: sources -> normalize -> EXCLUDE -> score -> route -> store.

Phase 0: sources/score/route are stubs. The exclusion gate is real (the one thing
that must work from day one).
"""
from __future__ import annotations

import logging
import uuid

from exclusions import is_excluded_company
from models import Job, RawJob
from store.repository import Repository, SqliteRepository

logger = logging.getLogger(__name__)


def sources() -> list[RawJob]:
    """Phase 1 will populate this from MyCareersFuture / LinkedIn."""
    return []


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
    )


def score(job: Job) -> float | None:
    """Phase 2 replaces this with the real scoring formula."""
    return None


def run(repo: Repository | None = None) -> dict[str, int]:
    repo = repo or SqliteRepository()
    processed = stored = excluded = skipped = 0
    for raw in sources():
        processed += 1
        if not (raw.company or "").strip():
            # Unidentifiable company — never act on it.
            logger.warning("Skipping job with no company: %s", raw.title)
            skipped += 1
            continue
        if is_excluded_company(raw.company):
            excluded += 1
            continue
        job = normalize(raw)
        job.score = score(job)
        repo.upsert_job(job)
        stored += 1
    return {"processed": processed, "stored": stored, "excluded": excluded, "skipped": skipped}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run()
    print(
        f"processed={result['processed']} stored={result['stored']} "
        f"excluded={result['excluded']} skipped={result['skipped']}"
    )


if __name__ == "__main__":
    main()
