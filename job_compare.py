"""Read-only job-board comparison and application-history utilities.

The ``scan`` command fetches listings and updates the local tracker, but it never
applies, drafts outreach, or sends notifications.
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from pathlib import Path

from matching import find_description_matches, find_duplicate_job, merge_jobs, rank_description_matches
from models import Job, RawJob
from runner import DEFAULT_TERMS, normalize
from sources.efinancialcareers import EFinancialCareersSource
from sources.linkedin import LinkedInJobSource
from sources.mycareersfuture import MyCareersFutureSource
from store.repository import SqliteRepository


HANDLED_STATUSES = {
    "queued", "drafted", "approved", "submitted", "applied", "interviewing", "offer",
    "rejected", "closed",
}


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def fetch_comparison_jobs(
    max_age_days: int, *, include_descriptions: bool = True
) -> list[RawJob]:
    jobs = MyCareersFutureSource(
        DEFAULT_TERMS, max_age_days=max_age_days, enrich=include_descriptions
    ).fetch()
    token = os.environ.get("APIFY_TOKEN", "")
    if token:
        jobs.extend(LinkedInJobSource(
            token, DEFAULT_TERMS, max_age_days=max_age_days
        ).fetch())
    jobs.extend(EFinancialCareersSource(
        DEFAULT_TERMS,
        location=os.environ.get("EFINANCIALCAREERS_LOCATION", "Singapore"),
        max_age_days=max_age_days,
    ).fetch())
    return jobs


def store_listings(repo: SqliteRepository, raws: list[RawJob]) -> tuple[int, int]:
    added = duplicates = 0
    for raw in raws:
        if not raw.company.strip() or not raw.title.strip():
            continue
        incoming = normalize(raw)
        existing = repo.get_job_by_dedupe_key(incoming.dedupe_key)
        if existing is None:
            existing = find_duplicate_job(incoming, repo.list_jobs())
        if existing:
            incoming = merge_jobs(existing, incoming)
            incoming.dedupe_key = existing.dedupe_key
            duplicates += 1
        else:
            added += 1
        repo.upsert_job(incoming)
    return added, duplicates


def import_application_history(repo: SqliteRepository, csv_path: Path) -> tuple[int, int]:
    """Import company,title,status rows; unmatched rows are reported, not guessed."""
    updated = unmatched = 0
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            candidate = normalize(RawJob(
                source=row.get("source") or "application_history",
                company=row.get("company") or "",
                title=row.get("title") or "",
                url=row.get("url") or "",
            ))
            job = repo.get_job_by_dedupe_key(candidate.dedupe_key)
            if job is None:
                unmatched += 1
                continue
            job.status = (row.get("status") or "applied").strip().casefold()
            note = (row.get("notes") or "").strip()
            if note:
                job.notes = f"{job.notes}\n{note}".strip()
            repo.upsert_job(job)
            updated += 1
    return updated, unmatched


def comparison_markdown(jobs: list[Job]) -> str:
    jobs = sorted(
        jobs,
        key=lambda j: (j.posted_at is not None, j.posted_at or "", j.company_canonical),
        reverse=True,
    )
    board_counts = Counter(s for job in jobs for s in (job.sources or [job.source]))
    handled = sum(job.status.casefold() in HANDLED_STATUSES for job in jobs)
    cross_listed = sum(len(job.sources or [job.source]) > 1 for job in jobs)
    description_matches = find_description_matches(jobs)
    closest_matches = rank_description_matches(jobs, limit=10)
    lines = [
        "# Job board comparison",
        "",
        "Generated from the local private tracker.",
        "",
        f"Roles: {len(jobs)} | Handled: {handled} | Exact cross-listings: {cross_listed} "
        f"| Write-up candidates: {len(description_matches)}",
        "",
        "Boards: " + ", ".join(f"{name} {count}" for name, count in sorted(board_counts.items())),
        "",
        "## Likely duplicates from write-up similarity",
        "",
        "These are review candidates, not automatic merges. Compare responsibilities and "
        "requirements before applying.",
        "",
        "| Guidance | Similarity | First listing | Second listing |",
        "|---|---:|---|---|",
    ]
    if not description_matches:
        lines.append("| — | — | No strong cross-board write-up matches | — |")
    for match in description_matches:
        handled_pair = any(
            job.status.casefold() in HANDLED_STATUSES for job in (match.left, match.right)
        )
        guidance = "DO NOT APPLY until reviewed" if handled_pair else "Apply once after review"
        left_url = next(iter(match.left.source_urls.values()), match.left.url)
        right_url = next(iter(match.right.source_urls.values()), match.right.url)
        left_label = f"{match.left.company_canonical} — {match.left.title}".replace("|", "\\|")
        right_label = f"{match.right.company_canonical} — {match.right.title}".replace("|", "\\|")
        lines.append(
            f"| {guidance} | {match.description_similarity:.0%} full write-up; "
            f"{match.phrase_overlap:.0%} shared detailed phrases | [{left_label}]({left_url}) "
            f"| [{right_label}]({right_url}) |"
        )
    lines.extend([
        "",
        "## Closest cross-board write-ups",
        "",
        "These are the nearest description comparisons even when they are below the duplicate "
        "threshold. A low percentage means the responsibilities differ materially.",
        "",
        "| Full write-up | Shared phrases | Title | First listing | Second listing |",
        "|---:|---:|---:|---|---|",
    ])
    if not closest_matches:
        lines.append("| — | — | — | No cross-board descriptions available | — |")
    for match in closest_matches:
        left_url = next(iter(match.left.source_urls.values()), match.left.url)
        right_url = next(iter(match.right.source_urls.values()), match.right.url)
        left_label = f"{match.left.company_canonical} — {match.left.title}".replace("|", "\\|")
        right_label = f"{match.right.company_canonical} — {match.right.title}".replace("|", "\\|")
        lines.append(
            f"| {match.description_similarity:.0%} | {match.phrase_overlap:.0%} "
            f"| {match.title_similarity:.0%} "
            f"| [{left_label}]({left_url}) | [{right_label}]({right_url}) |"
        )
    lines.extend([
        "",
        "## All canonical roles",
        "",
        "| Action | Company | Role | Boards | Posted | Status | Links |",
        "|---|---|---|---|---|---|---|",
    ])
    for job in jobs:
        sources = job.sources or [job.source]
        urls = job.source_urls or {job.source: job.url}
        links = ", ".join(f"[{source}]({url})" for source, url in urls.items() if url)
        action = "DO NOT APPLY" if job.status.casefold() in HANDLED_STATUSES else "Review"
        title = job.title.replace("|", "\\|")
        company = job.company_canonical.replace("|", "\\|")
        posted = job.posted_at.date().isoformat() if job.posted_at else ""
        lines.append(
            f"| {action} | {company} | {title} | {', '.join(sources)} "
            f"| {posted} | {job.status} | {links} |"
        )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("JOBS_DB_PATH", "data/jobs.sqlite"))
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Fetch and compare the three job boards safely")
    scan.add_argument("--max-age-days", type=int, default=7)
    scan.add_argument("--output", default="data/job_comparison.md")
    scan.add_argument(
        "--titles-only", action="store_true",
        help="Skip description enrichment (faster, but disables new write-up comparisons)",
    )
    report = sub.add_parser("report", help="Regenerate the report without network access")
    report.add_argument("--output", default="data/job_comparison.md")
    history = sub.add_parser("import-history", help="Import prior application statuses from CSV")
    history.add_argument("csv_path", type=Path)
    return parser


def main() -> None:
    _load_env()
    args = _parser().parse_args()
    repo = SqliteRepository(args.db)
    if args.command == "scan":
        raws = fetch_comparison_jobs(
            args.max_age_days, include_descriptions=not args.titles_only
        )
        added, duplicates = store_listings(repo, raws)
        per_source = Counter(raw.source for raw in raws)
        breakdown = ", ".join(f"{name}={count}" for name, count in sorted(per_source.items()))
        print(
            f"Fetched {len(raws)} listings ({breakdown or 'no source results'}); "
            f"{added} new roles; {duplicates} duplicate search results/cross-listings."
        )
    elif args.command == "import-history":
        updated, unmatched = import_application_history(repo, args.csv_path)
        print(f"Updated {updated} roles; {unmatched} history rows were unmatched.")
        return

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(comparison_markdown(repo.list_jobs()), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
