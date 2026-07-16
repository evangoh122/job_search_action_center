"""Pipeline orchestrator: sources -> normalize -> EXCLUDE -> score -> route -> store.

Phase 0: sources/score/route are stubs. The exclusion gate is real (the one thing
that must work from day one).
"""
from __future__ import annotations

import logging
import uuid

from datetime import datetime, timedelta

from apply.draft import ApplicationDraftQueue
from apply.resume_models import ResumeAchievement
from apply.tailor import tailor
from config import DAILY_CAPS, MINIMUM_MONTHLY_SGD
from exclusions import is_excluded_company
from models import Job, RawJob
from matching import find_duplicate_job, job_identity_key, merge_jobs
from network.email_finder import HunterEmailFinder
from network.outreach import build_drafts
from routing import apply_tier, should_outreach
from salary import SalaryRange, is_below_monthly_sgd_floor
from scoring import final_score
from sources.efinancialcareers import EFinancialCareersSource
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
    "ai product",
    "ai business",
    "head of ai",
    "director ai",
    "data analyst",
    "data scientist",
    "solutions architect ai",
    "cloud data architect",
    "principal data scientist",
    "staff data scientist",
    "ai platform lead",
    "product analytics lead",
    "customer engineer data ai",
    "technical account manager ai",
]


def sources(apify_token: str = "", include_greenhouse: bool = True) -> list[RawJob]:
    """Live job sources: MyCareersFuture (SG) + LinkedIn (when APIFY_TOKEN is set)
    + Greenhouse (large-fintech boards) + eFinancialCareers. Each source is
    best-effort and isolated."""
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
        efc_loc = os.environ.get("EFINANCIALCAREERS_LOCATION", "Singapore")
        efc_jobs = EFinancialCareersSource(
            DEFAULT_TERMS,
            location=efc_loc,
            max_age_days=int(os.environ.get("EFINANCIALCAREERS_MAX_AGE_DAYS", "7")),
        ).fetch()
        jobs.extend(efc_jobs)
        logger.info("eFinancialCareers source added %d jobs", len(efc_jobs))
    except Exception:
        logger.warning("eFinancialCareers source failed - continuing without it", exc_info=True)
    try:
        from sources.workday import WorkdaySource

        # Workday financial-employer discovery is deliberately Singapore-only.
        wd_loc = _workday_location()
        wd_jobs = WorkdaySource(location_contains=wd_loc).fetch()
        jobs.extend(wd_jobs)
        logger.info("Workday source added %d jobs", len(wd_jobs))
    except Exception:
        logger.warning("Workday source failed — continuing without it", exc_info=True)
    return jobs


def _workday_location() -> str:
    """Return the mandatory Singapore location filter for Workday bank searches."""
    import os

    configured = os.environ.get("WORKDAY_LOCATION", "Singapore").strip()
    if configured.casefold() != "singapore":
        logger.warning(
            "Ignoring WORKDAY_LOCATION=%r; bank Workday discovery is Singapore-only",
            configured,
        )
    return "Singapore"


def normalize(raw: RawJob) -> Job:
    """Normalize."""
    company = raw.company.strip()
    title = raw.title.strip()
    url = raw.url.strip()
    dedupe_key = job_identity_key(company, title)
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
        sources=[raw.source],
        source_urls={raw.source: url},
        salary_min=raw.salary_min,
        salary_max=raw.salary_max,
        salary_average=(raw.salary_min + raw.salary_max) / 2
        if raw.salary_min is not None and raw.salary_max is not None else None,
        salary_currency=raw.salary_currency,
        salary_period=raw.salary_period,
    )


def _within_24h(raw: RawJob) -> bool:
    """Within 24h."""
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


def _track_application_package(draft, tracker) -> None:
    """Track application package."""
    if tracker is None:
        return
    try:
        tracker.upsert_application(draft)
    except Exception:
        logger.warning("Sheets application-package upsert failed for %s", draft.title, exc_info=True)


def _run_apply_b(
    job,
    repo,
    apply_queue,
    base_summary,
    applicant_name,
    day,
    tracker=None,
    achievements: list[ResumeAchievement] | None = None,
) -> int:
    """Track 1, Tier B: tailor a cover letter and queue it for review (daily drafts cap)."""
    if apply_queue is None:
        return 0
    if repo.count_actions("drafts", day) >= DAILY_CAPS["drafts"]:
        logger.warning("Daily application-draft cap reached (%s)", DAILY_CAPS["drafts"])
        return 0
    draft = tailor(job, base_summary, applicant_name, achievements=achievements)
    apply_queue.add(draft)
    _track_application_package(draft, tracker)
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
    achievements: list[ResumeAchievement] | None = None,
) -> dict[str, int]:
    """Run."""
    repo = repo or SqliteRepository()
    raws = jobs if jobs is not None else sources(apify_token)
    day = datetime.now().date().isoformat()
    counts = {"processed": 0, "stored": 0, "duplicates": 0,
              "excluded": 0, "skipped": 0,
              "salary_filtered": 0,
              "qualified": 0, "tier_a": 0, "app_drafts": 0, "emails": 0, "posters": 0}
    new_jobs: list[Job] = []  # roles newly added to the tracker this run (for notifications)
    seen_this_run: set[str] = set()
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
        salary = SalaryRange(
            minimum=job.salary_min,
            maximum=job.salary_max,
            currency=job.salary_currency,
            period=job.salary_period,
        )
        if is_below_monthly_sgd_floor(salary, MINIMUM_MONTHLY_SGD):
            counts["salary_filtered"] += 1
            logger.info(
                "Salary floor filtered '%s' at %s (maximum %s %s)",
                job.title,
                job.company_canonical,
                job.salary_max,
                job.salary_period,
            )
            continue
        job.score = final_score(job, within_24h=_within_24h(raw))
        job.tier = apply_tier(job)
        existing = repo.get_job_by_dedupe_key(job.dedupe_key)
        if existing is None:
            existing = find_duplicate_job(job, repo.list_jobs())
        if existing is not None:
            job = merge_jobs(existing, job)
            job.dedupe_key = existing.dedupe_key
            counts["duplicates"] += 1
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
        duplicate_in_run = job.dedupe_key in seen_this_run
        seen_this_run.add(job.dedupe_key)
        approved_live = (
            auto_applier is not None
            and not auto_applier.dry_run
            and auto_applier.is_approved(job)
        )
        status = job.status.casefold()
        terminal_status = status in {
            "submitted", "applied", "interviewing", "offer", "rejected", "closed",
        }
        pending_status = status in {"queued", "drafted", "approved"}
        application_already_handled = terminal_status or (pending_status and not approved_live)

        if not duplicate_in_run and not application_already_handled and job.tier == "A":
            counts["tier_a"] += 1
            _track_application_package(
                tailor(job, base_summary, applicant_name, achievements=achievements), tracker
            )
            result = _run_apply_a(job, repo, auto_applier, day)
            if result == "submitted":
                job.status = "applied"
            # Top-priority bank role on a non-submittable ATS (LinkedIn/MCF): still draft it.
            if result in {
                "unsupported", "disabled", "incomplete", "approval_required",
                "review_required", "captcha_required", "error",
            }:
                drafted = 0
                if status == "new":
                    drafted = _run_apply_b(
                        job, repo, apply_queue, base_summary, applicant_name, day, tracker, achievements
                    )
                counts["app_drafts"] += drafted
                if drafted:
                    job.status = "drafted"
            repo.upsert_job(job)
        elif not duplicate_in_run and not application_already_handled and job.tier == "B":
            # Tier B remains draft-only unless this exact job has explicit approval and
            # live mode is enabled. Approval never broadens to another vacancy.
            if approved_live:
                _track_application_package(
                    tailor(job, base_summary, applicant_name, achievements=achievements), tracker
                )
            result = _run_apply_a(job, repo, auto_applier, day) if approved_live else "draft"
            if result == "submitted":
                job.status = "applied"
                repo.upsert_job(job)
            else:
                drafted = 0
                if status == "new":
                    drafted = _run_apply_b(
                        job, repo, apply_queue, base_summary, applicant_name, day, tracker, achievements
                    )
                counts["app_drafts"] += drafted
                if drafted:
                    job.status = "drafted"
                    repo.upsert_job(job)

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

    if tracker is not None:  # keep the Aging column live and sort the sheet
        try:
            tracker.refresh_aging_formulas()
            tracker.sort_jobs()
        except Exception:
            logger.warning("Sheets aging-formula refresh or sort failed", exc_info=True)

    counts["new"] = len(new_jobs)
    # Notify only for allowlisted companies (Notify-list.json / NOTIFY_COMPANIES).
    from notify_list import notify_company_match

    to_notify = [j for j in new_jobs if notify_company_match(j.company_canonical)]
    counts["notified"] = 0
    if notifier is not None and to_notify:
        try:
            counts["notified"] = notifier.send_new_jobs(to_notify)
        except Exception:
            logger.warning("New-role notification failed", exc_info=True)
    return counts


def _build_drafter_from_env():
    """Gmail drafts if OAuth refresh-token creds exist (preferred), else a single bearer
    token (GMAIL_TOKEN), else the local review-queue JSONL fallback."""
    import os

    from network.gmail_drafter import FallbackDrafter, GmailDrafter, ReviewQueueDrafter

    sender = os.environ.get("APPLICANT_EMAIL", "me") or "me"
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        logger.info("Gmail drafter: OAuth2 refresh-token flow.")
        return FallbackDrafter(
            GmailDrafter.from_refresh_token(
                client_id, client_secret, refresh_token, sender=sender
            ),
            ReviewQueueDrafter(),
        )
    gmail_token = os.environ.get("GMAIL_TOKEN")
    if gmail_token:
        logger.info("Gmail drafter: static bearer token.")
        return FallbackDrafter(
            GmailDrafter(gmail_token, sender=sender),
            ReviewQueueDrafter(),
        )
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
    """New-role notifier: Telegram if fully configured, else a local JSON feed (no setup)."""
    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        from network.telegram_notifier import TelegramNotifier
        logger.info("New-role notifications -> Telegram.")
        return TelegramNotifier(token, chat_id)
    from network.json_feed import JsonFeedNotifier

    path = os.environ.get("JSON_FEED_PATH", "data/new_roles.json")
    logger.info("New-role notifications -> JSON feed at %s", path)
    return JsonFeedNotifier(path)


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


def _load_resume_achievements_from_env() -> list[ResumeAchievement]:
    """Load the private evidence bank when configured; never block the job pipeline if absent."""
    import os
    from pathlib import Path

    from apply.resume_bank import load_achievements

    path = Path(os.environ.get("RESUME_ACHIEVEMENTS_PATH", "data/resume_achievements.json"))
    if not path.exists():
        logger.info("Resume achievement bank not found at %s; drafts will omit tailored evidence", path)
        return []
    try:
        return load_achievements(path)
    except (OSError, ValueError, TypeError):
        logger.warning("Resume achievement bank is invalid at %s; tailored evidence disabled", path)
        return []


def _build_auto_applier_from_env(achievements: list[ResumeAchievement] | None = None):
    """Build the approval-gated browser applier from local/CI environment settings."""
    import json
    import os
    from pathlib import Path

    from apply.auto_apply import AutoApplier, load_approval_keys
    from models import Applicant

    answers_raw = os.environ.get("APPLICATION_ANSWERS_JSON", "")
    answers: dict[str, str] = {}
    if answers_raw:
        try:
            answers = (
                json.loads(Path(answers_raw).read_text(encoding="utf-8"))
                if os.path.exists(answers_raw)
                else json.loads(answers_raw)
            )
        except (OSError, ValueError, TypeError):
            logger.warning("APPLICATION_ANSWERS_JSON is invalid; custom answers disabled.")

    applicant = Applicant(
        name=os.environ.get("APPLICANT_NAME", ""),
        email=os.environ.get("APPLICANT_EMAIL", ""),
        resume_url=os.environ.get("RESUME_URL", ""),
        resume_path=os.environ.get("RESUME_PATH", ""),
        phone=os.environ.get("APPLICANT_PHONE", ""),
        linkedin_url=os.environ.get("APPLICANT_LINKEDIN", ""),
        github_url=os.environ.get("APPLICANT_GITHUB", ""),
        location=os.environ.get("APPLICANT_LOCATION", "Singapore"),
        current_company=os.environ.get("APPLICANT_CURRENT_COMPANY", ""),
        work_authorization=os.environ.get("APPLICANT_WORK_AUTHORIZATION", ""),
        sponsorship_required=os.environ.get("APPLICANT_SPONSORSHIP_REQUIRED", ""),
        notice_period=os.environ.get("APPLICANT_NOTICE_PERIOD", ""),
        salary_expectation=os.environ.get("APPLICANT_SALARY_EXPECTATION", ""),
        answers=answers,
    )
    browser_submitter = None
    if os.environ.get("AUTO_APPLY_BROWSER", "").lower() == "true":
        from apply.browser_submitter import PlaywrightSubmitter

        browser_submitter = PlaywrightSubmitter(
            user_data_dir=os.environ.get("AUTO_APPLY_BROWSER_PROFILE", "data/browser_profile"),
            headless=os.environ.get("AUTO_APPLY_HEADLESS", "").lower() == "true",
            submit=True,
        )
    return AutoApplier(
        applicant,
        dry_run=os.environ.get("AUTO_APPLY_LIVE", "").lower() != "true",
        submitter=browser_submitter,
        approved_job_keys=load_approval_keys(os.environ.get("AUTO_APPLY_APPROVALS_FILE")),
        base_summary=os.environ.get("RESUME_SUMMARY", ""),
        draft_sink=ApplicationDraftQueue(
            os.environ.get("APPLICATION_DRAFTS_PATH", "data/application_drafts.jsonl")
        ).add,
        achievements=achievements or [],
    )


def main() -> None:
    """Run the command-line entry point."""
    logging.basicConfig(level=logging.INFO)
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv()  # load .env directly — no shell sourcing needed
    except ImportError:
        pass

    finder, drafter = _build_outreach_from_env()

    achievements = _load_resume_achievements_from_env()
    auto_applier = _build_auto_applier_from_env(achievements)

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
        achievements=achievements,
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
