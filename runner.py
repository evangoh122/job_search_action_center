"""Pipeline orchestrator: sources -> normalize -> EXCLUDE -> score -> route -> store.

Phase 0: sources/score/route are stubs. The exclusion gate is real (the one thing
that must work from day one).
"""
from __future__ import annotations

import logging
import uuid

from datetime import datetime, timedelta

from apply.draft import ApplicationDraftQueue
from apply.tailor import tailor
from config import DAILY_CAPS
from exclusions import is_excluded_company
from models import Job, RawJob
from network.email_finder import HunterEmailFinder
from network.outreach import build_drafts
from routing import apply_tier, should_outreach
from scoring import final_score
from sources.mycareersfuture import MyCareersFutureSource
from sources.linkedin import LinkedInJobSource
from store.repository import Repository, SqliteRepository

logger = logging.getLogger(__name__)

# Tuned to Evan's target: Data/AI VP & leadership roles in banks (SG-focused).
DEFAULT_TERMS = [
    "vice president data",
    "head of data",
    "head of analytics",
    "ai transformation",
    "data analytics lead",
    "vice president analytics",
    "head of data science",
    "director analytics",
]


def sources(apify_token: str = "") -> list[RawJob]:
    """Live job sources: MyCareersFuture (SG) + LinkedIn (when APIFY_TOKEN is set)."""
    jobs = MyCareersFutureSource(DEFAULT_TERMS, max_age_days=1).fetch()
    if apify_token:
        try:
            li_jobs = LinkedInJobSource(apify_token, DEFAULT_TERMS, max_age_days=1).fetch()
            jobs.extend(li_jobs)
            logger.info("LinkedIn source added %d jobs", len(li_jobs))
        except Exception:
            logger.warning("LinkedIn source failed — continuing with MCF only", exc_info=True)
    return jobs


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


def _run_apply_a(job, repo, auto_applier, day) -> str:
    """Track 1, Tier A: gated auto-apply (daily cap). Defaults to DRY_RUN via the applier."""
    if auto_applier is None:
        return "disabled"
    if repo.count_actions("auto_apply", day) >= DAILY_CAPS["auto_apply"]:
        logger.warning("Daily auto-apply cap reached (%s)", DAILY_CAPS["auto_apply"])
        return "capped"
    result = auto_applier.apply(job)
    if result in ("submitted", "dry_run"):
        repo.incr_action("auto_apply", day)
    return result


def _run_apply_b(job, repo, apply_queue, base_summary, applicant_name, day) -> int:
    """Track 1, Tier B: tailor a cover letter and queue it for review (daily drafts cap)."""
    if apply_queue is None:
        return 0
    if repo.count_actions("drafts", day) >= DAILY_CAPS["drafts"]:
        logger.warning("Daily application-draft cap reached (%s)", DAILY_CAPS["drafts"])
        return 0
    apply_queue.add(tailor(job, base_summary, applicant_name))
    repo.incr_action("drafts", day)
    return 1


def run(
    repo: Repository | None = None,
    jobs: list[RawJob] | None = None,
    finder=None,
    drafter=None,
    apply_queue=None,
    auto_applier=None,
    poster_finder=None,
    airtable=None,
    applicant_name: str = "",
    base_summary: str = "",
    apify_token: str = "",
) -> dict[str, int]:
    repo = repo or SqliteRepository()
    raws = jobs if jobs is not None else sources(apify_token)
    day = datetime.now().date().isoformat()
    counts = {"processed": 0, "stored": 0, "excluded": 0, "skipped": 0,
              "qualified": 0, "tier_a": 0, "app_drafts": 0, "emails": 0, "posters": 0}
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
        if airtable is not None:  # mirror to the Airtable job board
            try:
                airtable.upsert_job(job)
                counts["airtable"] = counts.get("airtable", 0) + 1
            except Exception:
                logger.warning("Airtable upsert failed for %s", job.title, exc_info=True)

        # Track 1 — apply
        if job.tier == "A":
            counts["tier_a"] += 1
            _run_apply_a(job, repo, auto_applier, day)
        elif job.tier == "B":
            counts["app_drafts"] += _run_apply_b(
                job, repo, apply_queue, base_summary, applicant_name, day
            )

        # Track 2 — outreach (parallel)
        if should_outreach(job):
            counts["qualified"] += 1
            counts["emails"] += _run_outreach(job, repo, finder, drafter, applicant_name, day)
            # Find the specific LinkedIn job poster to reach out to directly.
            if poster_finder is not None:
                poster = poster_finder.find_poster(job.url, company=job.company_canonical)
                if poster:
                    repo.upsert_contact(poster)
                    counts["posters"] += 1
                    logger.info("LinkedIn poster for '%s': %s (%s)",
                                job.title, poster.name, poster.role_type)
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

    try:
        from dotenv import load_dotenv
        load_dotenv()  # load .env directly — no shell sourcing needed
    except ImportError:
        pass

    finder, drafter = _build_outreach_from_env()

    # Tier A auto-apply: DRY_RUN unless AUTO_APPLY_LIVE=true is explicitly set.
    from apply.auto_apply import AutoApplier
    from models import Applicant

    applicant = Applicant(
        name=os.environ.get("APPLICANT_NAME", ""),
        email=os.environ.get("APPLICANT_EMAIL", ""),
        resume_url=os.environ.get("RESUME_URL", ""),
        linkedin_url=os.environ.get("APPLICANT_LINKEDIN", ""),
    )
    dry_run = os.environ.get("AUTO_APPLY_LIVE", "").lower() != "true"
    auto_applier = AutoApplier(applicant, dry_run=dry_run)

    # LinkedIn job-poster discovery (Phase 8) — enabled only if APIFY_TOKEN is set.
    poster_finder = None
    apify = os.environ.get("APIFY_TOKEN")
    if apify:
        from network.linkedin_poster import LinkedInPosterFinder
        poster_finder = LinkedInPosterFinder(apify)

    # Airtable job board — enabled if token + base id are set.
    airtable = None
    at_token, at_base = os.environ.get("AIRTABLE_TOKEN"), os.environ.get("AIRTABLE_BASE_ID")
    if at_token and at_base:
        from store.airtable_repo import AirtableRepository
        airtable = AirtableRepository(
            at_token, at_base, os.environ.get("AIRTABLE_JOBS_TABLE", "Jobs")
        )

    repo = SqliteRepository(os.environ.get("JOBS_DB_PATH", "data/jobs.sqlite"))
    result = run(
        repo=repo,
        finder=finder,
        drafter=drafter,
        apply_queue=ApplicationDraftQueue(),
        auto_applier=auto_applier,
        poster_finder=poster_finder,
        airtable=airtable,
        applicant_name=os.environ.get("APPLICANT_NAME", ""),
        base_summary=os.environ.get("RESUME_SUMMARY", ""),
        apify_token=apify or "",
    )
    from report import build_report

    print(build_report(result, repo.list_jobs()))
    print(
        f"processed={result['processed']} stored={result['stored']} "
        f"excluded={result['excluded']} skipped={result['skipped']} "
        f"tier_a={result['tier_a']} app_drafts={result['app_drafts']} "
        f"qualified={result['qualified']} emails={result['emails']}"
    )


if __name__ == "__main__":
    main()
