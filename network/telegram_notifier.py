"""Telegram notifications for newly-discovered roles you can apply for.

After a run, the pipeline sends a digest of the *new* jobs (ones not already in the
tracker) to a Telegram chat, each with company, title, score and an apply link — so you
monitor the feeds and apply yourself (no auto-apply).

Setup: create a bot via @BotFather -> TELEGRAM_BOT_TOKEN; get your chat id (message the
bot, then read it from https://api.telegram.org/bot<token>/getUpdates) -> TELEGRAM_CHAT_ID.
HTTP is injectable for tests.
"""
from __future__ import annotations

import html
import logging
from collections.abc import Callable

import httpx

from models import Job

logger = logging.getLogger(__name__)

HttpFn = Callable[[str, dict], dict]  # (url, json_body) -> response
_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX = 3800  # Telegram caps a message at 4096 chars; stay under with headroom


def _default_http(url: str, body: dict) -> dict:
    """Post one Telegram Bot API request and decode the response."""
    resp = httpx.post(url, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


class TelegramNotifier:
    """Send bounded HTML digests of newly discovered jobs to Telegram."""

    def __init__(self, token: str, chat_id: str, http: HttpFn | None = None) -> None:
        """Configure the bot token, destination chat, and HTTP transport."""
        self.token = token
        self.chat_id = chat_id
        self.http = http or _default_http

    @staticmethod
    def _line(job: Job) -> str:
        """Render one escaped job line for Telegram HTML mode."""
        score = f"{job.score:.0f}" if job.score is not None else "—"
        title = html.escape(job.title)
        company = html.escape(job.company_canonical)
        url = job.url or ""
        # HTML parse mode: clickable title, with score + company.
        link = f'<a href="{html.escape(url)}">{title}</a>' if url else title
        return f"• {link}\n  {company} · score {score} · {job.source}"

    def _send(self, text: str) -> None:
        """Send one already-bounded Telegram message chunk."""
        self.http(_API.format(token=self.token), {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })

    def send_new_jobs(self, jobs: list[Job]) -> int:
        """Send a digest of new roles, chunked to fit Telegram's message limit.
        Returns the number of jobs notified."""
        if not jobs:
            return 0
        header = f"🆕 {len(jobs)} new role(s) to apply for"
        lines = [self._line(j) for j in jobs]
        chunk = header
        for line in lines:
            if len(chunk) + len(line) + 2 > _MAX:
                self._send(chunk)
                chunk = ""
            chunk = f"{chunk}\n\n{line}" if chunk else line
        if chunk:
            self._send(chunk)
        logger.info("Telegram: notified %d new roles", len(jobs))
        return len(jobs)
