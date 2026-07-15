"""Discover LinkedIn posts matching tracked vacancies and create a review packet."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from network.linkedin_post_matcher import LinkedInPostMatcher
from network.networking_templates import create_post_grounded_linkedin_draft
from store.repository import SqliteRepository

_TERMINAL = {"submitted", "applied", "interviewing", "offer", "rejected", "closed"}


def render_packet(matches, applicant_name: str, applicant_proof: str, relevance: str) -> str:
    lines = [
        "# LinkedIn vacancy-post matches", "",
        "Every result requires review. No connection request or message was sent.", "",
    ]
    for index, match in enumerate(matches, 1):
        lines.extend([
            f"## {index}. {match.company} — {match.job_title}", "",
            f"Confidence: **{match.confidence:.0%}**", "",
            f"Evidence: {', '.join(match.evidence)}", "",
            f"Intent: **{match.post_intent}**", "",
            f"Job: {match.job_url}", "", f"Post: {match.post_url}", "",
            f"Author: {match.author_name or 'Unknown'} — {match.author_title or 'title unavailable'}", "",
            f"Profile: {match.author_profile_url or 'unavailable'}", "",
            "### Post", "", match.post_text, "",
        ])
        try:
            draft = create_post_grounded_linkedin_draft(
                match, applicant_name, applicant_proof, relevance)
            lines.extend(["### Post-grounded LinkedIn draft", "", draft, ""])
        except ValueError:
            lines.extend([
                "### Draft blocked", "",
                "Set NETWORKING_APPLICANT_PROOF and NETWORKING_RELEVANCE; generic outreach "
                "is intentionally not generated.", "",
            ])
        lines.extend(["Status: **REVIEW REQUIRED**", "", "---", ""])
    if not matches:
        lines.extend(["No credible matching posts were found in this run.", ""])
    return "\n".join(lines)


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("JOBS_DB_PATH", "data/jobs.sqlite"))
    parser.add_argument("--max-jobs", type=int, default=5)
    parser.add_argument("--max-posts", type=int, default=10)
    parser.add_argument("--posted-limit", default="week")
    parser.add_argument("--min-confidence", type=float, default=0.72)
    parser.add_argument("--output", default="data/linkedin_post_matches.md")
    args = parser.parse_args()
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_packet([], os.environ.get("APPLICANT_NAME", "Evan"), "", ""),
                          encoding="utf-8")
        print("APIFY_TOKEN is not configured; wrote an empty review packet.")
        return

    repo = SqliteRepository(args.db)
    eligible = [job for job in repo.list_jobs()
                if job.status.casefold() not in _TERMINAL and job.tier in {"A", "B"}]
    eligible.sort(key=lambda job: (job.score or 0, job.posted_at or ""), reverse=True)
    matcher = LinkedInPostMatcher(token, max_posts=args.max_posts, posted_limit=args.posted_limit)
    matches = []
    for job in eligible[:max(0, args.max_jobs)]:
        for match in matcher.find_matches(job):
            if match.confidence < args.min_confidence:
                continue
            repo.upsert_linkedin_post_match(match)
            matches.append(match)

    try:
        from runner import _build_sheets_from_env
        tracker = _build_sheets_from_env()
    except Exception:
        tracker = None
    if tracker is not None:
        for match in matches:
            tracker.upsert_linkedin_post_match(match)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_packet(
        matches,
        os.environ.get("APPLICANT_NAME", "Evan"),
        os.environ.get("NETWORKING_APPLICANT_PROOF", ""),
        os.environ.get("NETWORKING_RELEVANCE", ""),
    ), encoding="utf-8")
    print(f"Wrote {len(matches)} LinkedIn post match(es) to {output}")


if __name__ == "__main__":
    main()
