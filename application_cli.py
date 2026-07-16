"""Manage per-job approvals for browser-assisted applications."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from apply.auto_apply import load_approval_keys, load_salary_override_keys
from store.repository import SqliteRepository


def _write_approvals(
    path: Path, approvals: set[str], salary_overrides: set[str]
) -> None:
    """Write application approvals and separate salary-review overrides."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "approved": sorted(approvals),
                "salary_overrides": sorted(salary_overrides),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    """Parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("JOBS_DB_PATH") or "data/jobs.sqlite")
    parser.add_argument(
        "--approvals",
        default=os.environ.get("AUTO_APPLY_APPROVALS_FILE") or "data/application_approvals.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("eligible", help="List new Tier-A/B jobs and their approval keys")
    approve = sub.add_parser("approve", help="Approve exactly one job id or dedupe key")
    approve.add_argument("key")
    revoke = sub.add_parser("revoke", help="Remove a job approval")
    revoke.add_argument("key")
    salary_override = sub.add_parser(
        "salary-override",
        help="Record explicit salary review for one job with unknown/unparseable pay",
    )
    salary_override.add_argument("key")
    salary_revoke = sub.add_parser(
        "salary-override-revoke", help="Remove a recorded salary override"
    )
    salary_revoke.add_argument("key")
    apply = sub.add_parser("apply", help="Run only one existing tracker job through the applier")
    apply.add_argument("key")
    sub.add_parser("list", help="List current approval keys")
    return parser


def main() -> None:
    """Run the command-line entry point."""
    args = _parser().parse_args()
    path = Path(args.approvals)
    approvals = load_approval_keys(path)
    salary_overrides = load_salary_override_keys(path)
    if args.command == "approve":
        approvals.add(args.key)
        _write_approvals(path, approvals, salary_overrides)
        print(f"Approved {args.key}")
        return
    if args.command == "revoke":
        approvals.discard(args.key)
        _write_approvals(path, approvals, salary_overrides)
        print(f"Revoked {args.key}")
        return
    if args.command == "salary-override":
        salary_overrides.add(args.key)
        _write_approvals(path, approvals, salary_overrides)
        print(f"Recorded salary override for {args.key}")
        return
    if args.command == "salary-override-revoke":
        salary_overrides.discard(args.key)
        _write_approvals(path, approvals, salary_overrides)
        print(f"Revoked salary override for {args.key}")
        return
    if args.command == "list":
        for key in sorted(approvals):
            print(key)
        return

    repo = SqliteRepository(args.db)
    if args.command == "apply":
        job = next(
            (item for item in repo.list_jobs() if item.id == args.key or item.dedupe_key == args.key),
            None,
        )
        if job is None:
            raise SystemExit(f"No tracker job found for key: {args.key}")
        from runner import _build_auto_applier_from_env, _build_sheets_from_env

        applier = _build_auto_applier_from_env()
        result = applier.apply(job)
        tracker = _build_sheets_from_env()
        if tracker is not None and applier.last_draft is not None:
            tracker.upsert_application(applier.last_draft)
        if result == "submitted":
            job.status = "applied"
            repo.upsert_job(job)
        elif result == "submission_unknown":
            job.status = "submission_unknown"
            repo.upsert_job(job)
        print(f"{result}\t{job.company_canonical}\t{job.title}")
        if result in {
            "error",
            "incomplete",
            "unsupported",
            "salary_review_required",
            "captcha_required",
            "review_required",
            "submission_unknown",
        }:
            raise SystemExit(1)
        return

    eligible = [
        job for job in repo.list_jobs()
        if job.tier in {"A", "B"}
        and job.status.casefold() not in {
            "submission_unknown", "submitted", "applied", "interviewing", "offer",
            "rejected", "closed"
        }
    ]
    for job in sorted(eligible, key=lambda item: item.score or 0, reverse=True):
        marker = "APPROVED" if job.id in approvals or job.dedupe_key in approvals else "REVIEW"
        print(
            f"{marker}\t{job.status}\tTier {job.tier}\t{job.score or 0:.1f}\t"
            f"{job.company_canonical}\t{job.title}\t"
            f"{job.dedupe_key}\t{job.url}"
        )


if __name__ == "__main__":
    main()
