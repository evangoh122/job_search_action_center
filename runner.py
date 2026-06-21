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


def sources(apify_token: str = "", include_greenhouse: bool = True) -> list[RawJob]:
    """Live job sources: MyCareersFuture (SG) + LinkedIn (when APIFY_TOKEN is set)
    + Greenhouse (large-fintech boards). Each source is best-effort and isolated."""
    import os

    jobs = MyCareersFutureSource(DEFAULT_TERMS, max_age_days=1).fetch()
    if apify_token:
        try:
            li_jobs = LinkedInJobSource(apify_token, DEFAULT_TERMS, max_age_days=1).fetch()
            jobs.extend(li_jobs)
            logger.info("LinkedIn source added %d jobs", len(li_jobs))
        except Exception:
            logger.warning("LinkedIn source failed — continuing with MCF only", exc_info=True)
    if include_greenhouse:
        try:
            from sources.greenhouse import GreenhouseSource

            # GREENHOUSE_LOCATION="" disables the location filter (pull all geos).
            loc = os.environ.get("GREENHOUSE_LOCATION", "Singapore") or None
            gh_jobs = GreenhouseSource(location_contains=loc, max_age_days=7).fetch()
            jobs.extend(gh_jobs)
            logger.info("Greenhouse source added %d jobs", len(gh_jobs))
        except Exception:
            logger.warning("Greenhouse source failed — continuing without it", exc_info=True)
    try:
        from sources.workday import WorkdaySource

        # Target banks on Workday (Citi, Deutsche Bank, Morgan Stanley, ...).
        wd_loc = os.environ.get("WORKDAY_LOCATION", "Singapore") or None
        wd_jobs = WorkdaySource(location_contains=wd_loc).fetch()
        jobs.extend(wd_jobs)
        logger.info("Workday source added %d jobs", len(wd_jobs))
    except Exception:
        logger.warning("Workday source failed — continuing without it", exc_info=True)
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


def _track_contact(c, crm, tracker) -> str | None:
    """Mirror a contact into HubSpot (open-tracking) + the Sheets tracker. Returns its key."""
    if crm is not None:
        try:
            crm.upsert_contact(c)
        except Exception:
            logger.warning("HubSpot contact upsert failed for %s", c.email or c.name, exc_info=True)
    if tracker is not None:
        try:
            return tracker.upsert_contact(c)
        except Exception:
            logger.warning("Sheets contact upsert failed for %s", c.email or c.name, exc_info=True)
    return None


def _run_outreach(job, repo, finder, drafter, applicant_name, day,
                  crm=None, tracker=None, job_rec_id=None) -> int:
    """Track 2: email recruiter + hiring manager, respecting the daily outreach cap.
    Contacts are mirrored to HubSpot (open-tracking) + Google Sheets; each email is logged."""
    if finder is None or drafter is None:
        return 0
    contacts = finder.find_people(job.company_canonical, max_each=1)
    contact_rec_by_email = {}
    for c in contacts:
        rec = _track_contact(c, crm, tracker)
        if rec and c.email:
            contact_rec_by_email[c.email] = rec
    drafted = 0
    for draft in build_drafts(job, contacts, applicant_name):
        if repo.count_actions("outreach", day) >= DAILY_CAPS["outreach"]:
            logger.warning("Daily outreach cap reached (%s)", DAILY_CAPS["outreach"])
            break
        drafter.create_draft(draft)
        repo.incr_action("outreach", day)
        if tracker is not None:
            try:
                tracker.record_outreach(draft, job_rec_id, contact_rec_by_email.get(draft.to_email))
            except Exception:
                logger.warning("Sheets outreach log failed for %s", draft.to_email, exc_info=True)
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
    tracker=None,
    notifier=None,
    crm=None,
    applicant_name: str = "",
    base_summary: str = "",
    apify_token: str = "",
) -> dict[str, int]:
    repo = repo or SqliteRepository()
    raws = jobs if jobs is not None else sources(apify_token)
    day = datetime.now().date().isoformat()
    counts = {"processed": 0, "stored": 0, "excluded": 0, "skipped": 0,
              "qualified": 0, "tier_a": 0, "app_drafts": 0, "emails": 0, "posters": 0}
    new_jobs: list[Job] = []  # roles newly added to the tracker this run (for notifications)
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
        job_rec_id = None
        if tracker is not None:  # mirror to the Google Sheets job board
            try:
                job_rec_id = tracker.upsert_job(job)
                counts["sheets"] = counts.get("sheets", 0) + 1
                if getattr(tracker, "last_was_new", False):
                    new_jobs.append(job)
            except Exception:
                logger.warning("Sheets upsert failed for %s", job.title, exc_info=True)

        # Track 1 — apply
        if job.tier == "A":
            counts["tier_a"] += 1
            result = _run_apply_a(job, repo, auto_applier, day)
            # Top-priority bank role on a non-submittable ATS (LinkedIn/MCF): still draft it.
            if result in ("unsupported", "disabled"):
                counts["app_drafts"] += _run_apply_b(
                    job, repo, apply_queue, base_summary, applicant_name, day
                )
        elif job.tier == "B":
            counts["app_drafts"] += _run_apply_b(
                job, repo, apply_queue, base_summary, applicant_name, day
            )

        # Track 2 — outreach (parallel)
        if should_outreach(job):
            counts["qualified"] += 1
            counts["emails"] += _run_outreach(
                job, repo, finder, drafter, applicant_name, day,
                crm=crm, tracker=tracker, job_rec_id=job_rec_id,
            )
            # Find the specific LinkedIn job poster to reach out to directly.
            if poster_finder is not None:
                poster = poster_finder.find_poster(job.url, company=job.company_canonical)
                if poster:
                    repo.upsert_contact(poster)
                    _track_contact(poster, crm, tracker)  # mirror to HubSpot + Sheets
                    counts["posters"] += 1
                    logger.info("LinkedIn poster for '%s': %s (%s)",
                                job.title, poster.name, poster.role_type)

    if tracker is not None:  # keep the Aging column live (formula recomputes daily)
        try:
            tracker.refresh_aging_formulas()
        except Exception:
            logger.warning("Sheets aging-formula refresh failed", exc_info=True)

    counts["new"] = len(new_jobs)
    if notifier is not None and new_jobs:  # ping new roles to apply for
        try:
            notifier.send_new_jobs(new_jobs)
        except Exception:
            logger.warning("Telegram notification failed", exc_info=True)
    return counts


def _build_drafter_from_env():
    """Gmail drafts if OAuth refresh-token creds exist (preferred), else a single bearer
    token (GMAIL_TOKEN), else the local review-queue JSONL fallback."""
    import os

    from network.gmail_drafter import GmailDrafter, ReviewQueueDrafter

    sender = os.environ.get("APPLICANT_EMAIL", "me") or "me"
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        logger.info("Gmail drafter: OAuth2 refresh-token flow.")
        return GmailDrafter.from_refresh_token(
            client_id, client_secret, refresh_token, sender=sender
        )
    gmail_token = os.environ.get("GMAIL_TOKEN")
    if gmail_token:
        logger.info("Gmail drafter: static bearer token.")
        return GmailDrafter(gmail_token, sender=sender)
    logger.info("Gmail not configured — using local review-queue JSONL fallback.")
    return ReviewQueueDrafter()


def _build_sheets_from_env():
    """Google Sheets tracker if a service account + spreadsheet id are configured.

    GOOGLE_SERVICE_ACCOUNT_JSON may be a path to the key file or the raw JSON itself
    (handy for CI secrets). Returns None when not configured, so the apply track still runs.
    """
    import json
    import os

    sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not (sa and spreadsheet_id):
        logger.info("Google Sheets not configured — tracker disabled (apply track still runs).")
        return None
    from store.google_sheets_repo import GoogleSheetsRepository

    try:
        if os.path.exists(sa):
            return GoogleSheetsRepository.from_service_account_file(sa, spreadsheet_id)
        return GoogleSheetsRepository.from_service_account_info(json.loads(sa), spreadsheet_id)
    except Exception:
        logger.warning("Google Sheets auth failed — tracker disabled.", exc_info=True)
        return None


def _build_notifier_from_env():
    """Telegram notifier if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set, else None."""
    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        logger.info("Telegram not configured — new-role notifications disabled.")
        return None
    from network.telegram_notifier import TelegramNotifier

    return TelegramNotifier(token, chat_id)


def _build_outreach_from_env():
    """Enable Track 2 only if a Hunter key exists; pick the best available Gmail drafter."""
    import os

    hunter = os.environ.get("HUNTER_API_KEY")
    if not hunter:
        logger.info("HUNTER_API_KEY not set — outreach track disabled (apply track still runs).")
        return None, None
    from network.email_finder import HunterEmailFinder

    finder = HunterEmailFinder(hunter)
    drafter = _build_drafter_from_env()
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

    # Google Sheets job board — enabled if a service account + spreadsheet id are set
    # (Jobs + Contacts + Outreach tabs, auto-created on first run).
    tracker = _build_sheets_from_env()

    # HubSpot CRM — used only to mirror contacts so the Gmail Sales extension tracks opens.
    crm = None
    hubspot_token = os.environ.get("HUBSPOT_TOKEN")
    if hubspot_token:
        from store.hubspot_repo import HubSpotRepository
        crm = HubSpotRepository(hubspot_token)

    repo = SqliteRepository(os.environ.get("JOBS_DB_PATH", "data/jobs.sqlite"))
    result = run(
        repo=repo,
        finder=finder,
        drafter=drafter,
        apply_queue=ApplicationDraftQueue(),
        auto_applier=auto_applier,
        poster_finder=poster_finder,
        tracker=tracker,
        notifier=_build_notifier_from_env(),
        crm=crm,
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
