"""Turn EmailDrafts into Gmail drafts (human approves & sends) — or a local review queue
when Gmail isn't configured. Drafts only: nothing is ever auto-sent (PLAN.md §3 Track 2).
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

import httpx

from models import EmailDraft

logger = logging.getLogger(__name__)

HttpFn = Callable[[str, str, dict | None], dict]  # (method, url, json_body) -> response


class Drafter(Protocol):
    def create_draft(self, draft: EmailDraft) -> str: ...


def _to_mime_base64url(draft: EmailDraft, sender: str) -> str:
    msg = EmailMessage()
    msg["To"] = draft.to_email
    msg["From"] = sender
    msg["Subject"] = draft.subject
    msg.set_content(draft.body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GmailDrafter:
    """Creates a Gmail draft via the Gmail API. Needs OAuth (compose scope). Injectable HTTP."""

    def __init__(self, token: str, sender: str = "me", http: HttpFn | None = None):
        self.token = token
        self.sender = sender
        self.http = http or self._default_http

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def create_draft(self, draft: EmailDraft) -> str:
        raw = _to_mime_base64url(draft, self.sender)
        res = self.http(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            {"message": {"raw": raw}},
        )
        return res.get("id", "")


class ReviewQueueDrafter:
    """No-Gmail fallback: append drafts to a JSONL file for manual review/send."""

    def __init__(self, path: str = "data/outreach_drafts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create_draft(self, draft: EmailDraft) -> str:
        draft_id = str(uuid.uuid4())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": draft_id, **draft.model_dump()}) + "\n")
        return draft_id
