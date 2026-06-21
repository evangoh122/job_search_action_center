"""JSON feed of new roles to apply for — the no-setup alternative to Telegram.

Each run appends the newly-discovered roles (ones not already in the tracker) to a rolling
JSON feed, newest first, deduped by URL and capped to the most recent entries. Open the
file directly, commit it, or serve it as a lightweight "new roles" feed.

Shape:
    {"generated_at": "...", "new_this_run": N, "roles": [
        {"title","company","score","tier","source","ats_type","url","posted_at","first_seen"}
    ]}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from models import Job

logger = logging.getLogger(__name__)


class JsonFeedNotifier:
    def __init__(self, path: str = "data/new_roles.json", max_entries: int = 200) -> None:
        self.path = Path(path)
        self.max_entries = max_entries

    @staticmethod
    def _entry(job: Job, first_seen: str) -> dict:
        return {
            "title": job.title,
            "company": job.company_canonical,
            "score": round(job.score, 1) if job.score is not None else None,
            "tier": job.tier,
            "source": job.source,
            "ats_type": job.ats_type,
            "url": job.url,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "first_seen": first_seen,
        }

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("roles", [])
        except (ValueError, OSError):
            logger.warning("Could not read existing feed at %s — starting fresh", self.path)
            return []

    def send_new_jobs(self, jobs: list[Job]) -> int:
        """Merge new roles into the feed (newest first, deduped by URL). Returns count added."""
        if not jobs:
            return 0
        now = datetime.now().isoformat(timespec="seconds")
        # New entries first, then prior ones (a repeated URL keeps the new entry).
        by_url: dict[str, dict] = {}
        for job in jobs:
            e = self._entry(job, now)
            by_url[job.url or job.dedupe_key] = e
        for prior in self._load():
            key = prior.get("url") or prior.get("title") or ""
            if key:
                by_url.setdefault(key, prior)
        roles = sorted(by_url.values(), key=lambda r: r.get("first_seen", ""), reverse=True)
        roles = roles[: self.max_entries]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"generated_at": now, "new_this_run": len(jobs), "roles": roles},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("JSON feed: +%d new roles -> %s (%d total)", len(jobs), self.path, len(roles))
        return len(jobs)
