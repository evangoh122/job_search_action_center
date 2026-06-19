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
TokenPost = Callable[[str, dict], dict]  # (url, form_data) -> response

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"


class Drafter(Protocol):
    def create_draft(self, draft: EmailDraft) -> str: ...


def _to_mime_base64url(draft: EmailDraft, sender: str) -> str:
    msg = EmailMessage()
    msg["To"] = draft.to_email
    msg["From"] = sender
    msg["Subject"] = draft.subject
    msg.set_content(draft.body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _default_token_post(url: str, data: dict) -> dict:
    resp = httpx.post(url, data=data, timeout=30)  # token endpoint takes form-encoded
    resp.raise_for_status()
    return resp.json()


def refresh_gmail_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    token_post: TokenPost | None = None,
) -> str:
    """Exchange a long-lived refresh token for a short-lived access token."""
    post = token_post or _default_token_post
    res = post(_TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    return res["access_token"]


class GmailDrafter:
    """Creates a Gmail draft via the Gmail API. Needs OAuth (compose scope). Injectable HTTP.

    Two ways to authenticate:
      - pass a ready bearer ``token`` (short-lived access token), or
      - use ``from_refresh_token(...)`` to supply OAuth client creds + refresh token;
        the access token is fetched lazily on first draft and cached for the run.
    """

    def __init__(
        self,
        token: str | None = None,
        sender: str = "me",
        http: HttpFn | None = None,
        token_provider: Callable[[], str] | None = None,
    ):
        self._cached_token = token
        self._token_provider = token_provider
        self.sender = sender
        self.http = http or self._default_http

    @classmethod
    def from_refresh_token(
        cls,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        sender: str = "me",
        http: HttpFn | None = None,
        token_post: TokenPost | None = None,
    ) -> "GmailDrafter":
        provider = lambda: refresh_gmail_access_token(  # noqa: E731
            client_id, client_secret, refresh_token, token_post
        )
        return cls(sender=sender, http=http, token_provider=provider)

    def _access_token(self) -> str:
        if self._cached_token is None and self._token_provider is not None:
            self._cached_token = self._token_provider()
        return self._cached_token or ""

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self._access_token()}",
                     "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def create_draft(self, draft: EmailDraft) -> str:
        raw = _to_mime_base64url(draft, self.sender)
        res = self.http("POST", _DRAFTS_URL, {"message": {"raw": raw}})
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
