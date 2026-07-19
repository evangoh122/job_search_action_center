"""Prepare, review, approve, and autofill exact job-application packages."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from apply.browser_submitter import PlaywrightApplicationFiller
from apply.review_engine import (
    ApplicationPackageStore,
    ApprovalStore,
    ReviewFirstApplicationEngine,
    review_package,
)
from store.repository import SqliteRepository
from models import ApplicationDraft


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("JOBS_DB_PATH") or "data/jobs.sqlite")
    parser.add_argument("--packages", default="data/application_packages")
    parser.add_argument("--approval-ledger", default="data/application_approvals_v2.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("eligible", help="List application candidates")

    prepare = sub.add_parser("prepare", help="Build and review an immutable package")
    prepare.add_argument("key", help="Job id or dedupe key")
    prepare.add_argument("--resume", required=True, help="Exact final PDF artifact to package")
    prepare.add_argument(
        "--salary-reviewed",
        action="store_true",
        help="Confirm you reviewed this vacancy despite unknown/unparseable salary",
    )

    for command, help_text in (
        ("show", "Show the exact packaged vacancy, answers, and artifact hashes"),
        ("review", "Re-run deterministic review against current artifact bytes"),
        ("sync", "Archive the exact résumé to Drive and sync the package to Sheets"),
        ("approve", "Create a short-lived, single-use approval for an exact package"),
        ("revoke", "Revoke an unused exact-package approval"),
        ("open", "Autofill a visible browser and pause for your final Submit click"),
        ("record-submitted", "Record that you manually submitted the package"),
        ("record-unknown", "Record an uncertain manual submission result"),
    ):
        command_parser = sub.add_parser(command, help=help_text)
        command_parser.add_argument("package_id")
        if command == "approve":
            command_parser.add_argument("--ttl-minutes", type=int, default=30)
    return parser


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _find_job(repo: SqliteRepository, key: str):
    return next(
        (job for job in repo.list_jobs() if job.id == key or job.dedupe_key == key),
        None,
    )


def _engine(args) -> ReviewFirstApplicationEngine:
    from runner import (
        _build_auto_applier_from_env,
        _build_sheets_from_env,
        _load_resume_achievements_from_env,
    )
    from store.google_drive_resume_archive import archive_resume_name
    from datetime import datetime

    achievements = _load_resume_achievements_from_env()
    drafting_applier = _build_auto_applier_from_env(achievements)

    def validate_authority(package, archive, allowed_statuses):
        archiver = _build_resume_archive()
        expected_name = archive_resume_name(
            package.company,
            Path(package.resume_path).suffix,
            applicant="Evan Goh",
            date=datetime.fromisoformat(archive.archived_at),
        )
        archiver.validate_remote(archive, expected_name=expected_name)
        tracker = _build_sheets_from_env()
        if tracker is None:
            raise RuntimeError("authoritative Google Sheets validation is unavailable")
        tracker.validate_application_record(
            package_id=package.package_id,
            job_id=package.job_id,
            company=package.company,
            title=package.title,
            application_link=package.form_url,
            resume_filename=Path(package.resume_path).name,
            cover_letter=package.cover_letter,
            fields_hash=package.fields_hash,
            package_hash=package.expected_package_id(),
            resume_hash=package.resume_hash,
            resume_page_count=package.resume_page_count,
            drive_file_id=archive.drive_file_id,
            drive_url=archive.drive_url,
            drive_name=archive.drive_name,
            allowed_statuses=allowed_statuses,
        )

    return ReviewFirstApplicationEngine(
        drafting_applier.applicant,
        package_store=ApplicationPackageStore(args.packages),
        approval_store=ApprovalStore(args.approval_ledger),
        base_summary=drafting_applier.base_summary,
        achievements=achievements,
        authority_validator=validate_authority,
    )


def _print_review(package, review) -> None:
    print(f"Package: {package.package_id}")
    print(f"Role: {package.company} — {package.title}")
    print(f"Form: {package.form_url}")
    print(f"Resume SHA-256: {package.resume_hash}")
    print(f"Answers SHA-256: {package.fields_hash}")
    print(f"Review: {review.verdict.upper()}")
    for finding in review.findings:
        print(f"  {finding.severity.upper()}: {finding.message}")


def _build_resume_archive():
    from store.google_drive_resume_archive import (
        GoogleDriveResumeArchive,
        load_drive_archive_config,
    )

    service_account = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    config = load_drive_archive_config()
    folder_id = os.environ.get("APPLICATION_RESUME_DRIVE_FOLDER_ID", "") or config.get(
        "resume_folder_id", ""
    )
    if not folder_id:
        raise RuntimeError(
            "Drive archive requires APPLICATION_RESUME_DRIVE_FOLDER_ID"
        )
    oauth = (
        os.environ.get("GOOGLE_DRIVE_CLIENT_ID", ""),
        os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", ""),
        os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN", ""),
    )
    if all(oauth):
        return GoogleDriveResumeArchive.from_user_refresh_token(*oauth, folder_id)
    if not service_account:
        raise RuntimeError(
            "Drive archive requires Google user OAuth for My Drive, or a service account with a Shared Drive"
        )
    if os.path.exists(service_account):
        return GoogleDriveResumeArchive.from_service_account_file(service_account, folder_id)
    return GoogleDriveResumeArchive.from_service_account_info(json.loads(service_account), folder_id)


def _archive_resume(engine, package):
    archiver = _build_resume_archive()
    record = archiver.archive(
        package_id=package.package_id,
        company=package.company,
        resume_path=package.resume_path,
        expected_sha256=package.resume_hash,
        applicant=engine.applicant.name or "Evan Goh",
    )
    engine.package_store.record_drive_archive(record)
    return record, archiver


def _draft_from_package(package) -> ApplicationDraft:
    return ApplicationDraft(
        job_id=package.job_id,
        company=package.company,
        title=package.title,
        url=package.job_url,
        application_link=package.form_url,
        resume_filename=Path(package.resume_path).name,
        cover_letter=package.cover_letter,
    )


def _sync_to_sheets(engine, package, draft, review, archive, archiver) -> str:
    from runner import _build_sheets_from_env

    tracker = _build_sheets_from_env()
    if tracker is None:
        raise RuntimeError(
            "Google Sheets is not configured; set GOOGLE_SERVICE_ACCOUNT_JSON and SPREADSHEET_ID"
        )
    tracked = draft.model_copy(update={
        "application_link": package.form_url,
        "resume_filename": Path(package.resume_path).name,
        "status": "review_passed" if review.passed else "review_blocked",
        "package_id": package.package_id,
        "package_hash": package.expected_package_id(),
        "resume_hash": package.resume_hash,
        "resume_page_count": package.resume_page_count,
        "resume_drive_file_id": archive.drive_file_id,
        "resume_drive_url": archive.drive_url,
        "resume_archive_name": archive.drive_name,
        "fields_hash": package.fields_hash,
        "review_verdict": review.verdict,
    })
    record_key = tracker.upsert_application(
        tracked,
        resume_path=package.resume_path,
        archive=archive,
        drive_archive=archiver,
    )
    engine.package_store.record_sheets_sync(package.package_id, record_key)
    return record_key


def main() -> None:
    _load_dotenv()
    args = _parser().parse_args()
    repo = SqliteRepository(args.db)

    if args.command == "eligible":
        eligible = [
            job for job in repo.list_jobs()
            if job.tier in {"A", "B"}
            and job.status.casefold() not in {
                "submission_unknown", "submitted", "applied", "interviewing",
                "offer", "rejected", "closed",
            }
        ]
        for job in sorted(eligible, key=lambda item: item.score or 0, reverse=True):
            print(
                f"{job.status}\tTier {job.tier}\t{job.score or 0:.1f}\t"
                f"{job.company_canonical}\t{job.title}\t{job.dedupe_key}\t{job.url}"
            )
        return

    engine = _engine(args)
    if args.command == "prepare":
        job = _find_job(repo, args.key)
        if job is None:
            raise SystemExit(f"No tracker job found for key: {args.key}")
        package, review, draft, _ = engine.prepare(
            job,
            resume_path=args.resume,
            salary_override=args.salary_reviewed,
        )
        if not review.passed:
            _print_review(package, review)
            raise SystemExit("Package review blocked; nothing was archived as Resume Used")
        try:
            archive, archiver = _archive_resume(engine, package)
            print(f"Google Drive résumé: {archive.drive_name} — {archive.drive_url}")
            record_key = _sync_to_sheets(
                engine, package, draft, review, archive, archiver
            )
            print(f"Google Sheets row: {record_key}")
        except Exception as exc:
            _print_review(package, review)
            raise SystemExit(f"Package saved locally but approval blocked: archive/sync failed: {exc}")
        _print_review(package, review)
        if not review.passed:
            raise SystemExit(1)
        return

    package = engine.package_store.load_package(args.package_id)
    if args.command == "sync":
        review = review_package(package)
        engine.package_store.save_review(review)
        if not review.passed:
            _print_review(package, review)
            raise SystemExit("Sync blocked: application package review did not pass")
        archive, archiver = _archive_resume(engine, package)
        record_key = _sync_to_sheets(
            engine, package, _draft_from_package(package), review, archive, archiver
        )
        print(f"Google Drive résumé: {archive.drive_name} — {archive.drive_url}")
        print(f"Google Sheets row: {record_key}")
        return
    if args.command == "show":
        review = review_package(package)
        _print_review(package, review)
        print("Answers:")
        for key, value in sorted(package.fields.items()):
            print(f"  {key}: {value}")
        return
    if args.command == "review":
        review = review_package(package)
        engine.package_store.save_review(review)
        _print_review(package, review)
        if not review.passed:
            raise SystemExit(1)
        return
    if args.command == "approve":
        if not engine.package_store.sheets_sync_is_current(package):
            raise SystemExit("Approval blocked: exact package is not durably synced to Google Sheets")
        receipt = engine.approve(args.package_id, ttl_minutes=args.ttl_minutes)
        from runner import _build_sheets_from_env
        tracker = _build_sheets_from_env()
        if tracker is None:
            raise SystemExit("Approval recorded locally but Sheets status update failed")
        tracker.update_application_status(package.package_id, "approved")
        _print_review(package, engine.package_store.load_review(args.package_id))
        print(f"Approved once; expires {receipt.expires_at}; nonce {receipt.nonce}")
        return
    if args.command == "revoke":
        receipt = engine.revoke(args.package_id)
        print(f"Revoked {receipt.package_id} at {receipt.revoked_at or 'already consumed'}")
        return

    job = _find_job(repo, package.job_id)
    if job is None:
        raise SystemExit("Packaged vacancy no longer exists in the local tracker")
    if args.command == "open":
        filler = PlaywrightApplicationFiller(
            user_data_dir=os.environ.get("AUTO_APPLY_BROWSER_PROFILE", "data/browser_profile"),
            headless=False,
        )
        result = engine.open_for_review(args.package_id, job, filler)
        if result == "ready_for_manual_submit":
            from runner import _build_sheets_from_env
            tracker = _build_sheets_from_env()
            if tracker is None:
                raise SystemExit("Browser review completed but Sheets status update failed")
            tracker.update_application_status(package.package_id, "autofill_ready")
        print(f"{result}\t{package.company}\t{package.title}")
        if result != "ready_for_manual_submit":
            raise SystemExit(1)
        return
    if args.command in {"record-submitted", "record-unknown"}:
        receipt = engine.approval_store.get(package.package_id)
        if receipt is None or not receipt.consumed_at:
            raise SystemExit("Cannot record a result before the approved package was opened")
        status = "applied" if args.command == "record-submitted" else "submission_unknown"
        from runner import _build_sheets_from_env
        tracker = _build_sheets_from_env()
        if tracker is None:
            raise SystemExit("Cannot record result while authoritative Google Sheets is unavailable")
        tracker.update_application_status(package.package_id, status)
        job.status = status
        repo.upsert_job(job)
        print(f"Recorded {status}: {package.company} — {package.title}")
        return


if __name__ == "__main__":
    main()
