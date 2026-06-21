"""Scrape networking contacts out of Gmail to populate the orange "Networking Tracker" tab.

Pulls both directions over the last 12 months by default:
  - sent mail  -> the people you emailed (To + Cc)
  - received mail -> the people who emailed you (From)

Automated senders (no-reply, mailer-daemon, newsletters, notifications) are skipped, and
contacts are deduped by email, keeping the most recent contact date and the best name.

Auth mirrors gmail_drafter: pass a bearer ``token`` or use ``from_refresh_token`` with OAuth
client creds (needs the gmail.readonly scope). HTTP is injectable for tests.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import getaddresses, parsedate_to_datetime

from network.gmail_drafter import HttpFn, TokenPost, refresh_gmail_access_token

logger = logging.getLogger(__name__)

_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
_MSG_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"
_HEADERS = ("From", "To", "Cc", "Date")

# Local-parts / substrings that signal an automated, non-human sender.
_AUTOMATED = (
    "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "notification", "notifications", "newsletter", "updates", "alerts",
    "bounce", "automated", "support@", "info@", "hello@", "team@",
)
# Free providers we never treat as a company domain.
_FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "yahoo.com.sg", "icloud.com", "me.com", "proton.me", "protonmail.com", "live.com",
}


@dataclass
class NetworkContact:
    name: str
    email: str
    company: str = ""
    last_contacted: str = ""  # ISO date
    source: str = "gmail"


def _is_automated(name: str, email: str) -> bool:
    blob = f"{name} {email}".lower()
    return any(tag in blob for tag in _AUTOMATED)


def _company_from_email(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].lower()
    if domain in _FREE_PROVIDERS or "." not in domain:
        return ""
    label = domain.split(".")[-2] if len(domain.split(".")) >= 2 else domain
    return label.replace("-", " ").title()


def _parse_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return ""


class GmailNetworkScraper:
    def __init__(
        self,
        token: str | None = None,
        user_email: str = "",
        http: HttpFn | None = None,
        token_provider: Callable[[], str] | None = None,
        max_messages: int = 2000,
    ) -> None:
        self._cached_token = token
        self._token_provider = token_provider
        self.user_email = user_email.lower()
        self.http = http or self._default_http
        self.max_messages = max_messages

    @classmethod
    def from_refresh_token(
        cls,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        user_email: str = "",
        http: HttpFn | None = None,
        token_post: TokenPost | None = None,
        max_messages: int = 2000,
    ) -> "GmailNetworkScraper":
        provider = lambda: refresh_gmail_access_token(  # noqa: E731
            client_id, client_secret, refresh_token, token_post
        )
        return cls(user_email=user_email, http=http, token_provider=provider,
                   max_messages=max_messages)

    def _access_token(self) -> str:
        if self._cached_token is None and self._token_provider is not None:
            self._cached_token = self._token_provider()
        return self._cached_token or ""

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        import httpx

        resp = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _is_me(self, email: str) -> bool:
        return bool(self.user_email) and email.lower() == self.user_email

    def _list_message_ids(self, query: str) -> list[str]:
        ids: list[str] = []
        page_token = ""
        while len(ids) < self.max_messages:
            sep = "&" if "?" in _LIST_URL else "?"
            from urllib.parse import quote
            url = f"{_LIST_URL}{sep}q={quote(query)}&maxResults=500"
            if page_token:
                url += f"&pageToken={page_token}"
            res = self.http("GET", url, None)
            ids.extend(m["id"] for m in res.get("messages", []))
            page_token = res.get("nextPageToken", "")
            if not page_token:
                break
        return ids[: self.max_messages]

    def _message_headers(self, msg_id: str) -> dict[str, str]:
        from urllib.parse import urlencode

        params = urlencode([("format", "metadata"), *[("metadataHeaders", h) for h in _HEADERS]])
        url = f"{_MSG_URL.format(id=msg_id)}?{params}"
        payload = self.http("GET", url, None).get("payload", {})
        return {h["name"]: h["value"] for h in payload.get("headers", [])}

    def _merge(self, acc: dict[str, NetworkContact], name: str, email: str,
               date: str, source: str) -> None:
        email = email.lower().strip()
        if not email or self._is_me(email) or _is_automated(name, email):
            return
        existing = acc.get(email)
        if existing is None:
            acc[email] = NetworkContact(
                name=name.strip(), email=email,
                company=_company_from_email(email), last_contacted=date, source=source,
            )
            return
        if name.strip() and not existing.name:  # backfill a missing name
            existing.name = name.strip()
        if date > existing.last_contacted:  # keep most recent touch (ISO dates sort)
            existing.last_contacted = date
            existing.source = source

    def scrape(self, query: str = "newer_than:1y -in:chats") -> list[NetworkContact]:
        acc: dict[str, NetworkContact] = {}
        for msg_id in self._list_message_ids(query):
            headers = self._message_headers(msg_id)
            date = _parse_date(headers.get("Date"))
            from_pairs = getaddresses([headers.get("From", "")])
            sender_email = from_pairs[0][1].lower() if from_pairs else ""
            if self._is_me(sender_email):  # outbound — counterparts are recipients
                people = getaddresses([headers.get("To", ""), headers.get("Cc", "")])
                source = "gmail:sent"
            else:  # inbound — counterpart is the sender
                people = from_pairs
                source = "gmail:received"
            for name, email in people:
                self._merge(acc, name, email, date, source)
        contacts = sorted(acc.values(), key=lambda c: c.last_contacted, reverse=True)
        logger.info("Gmail network scrape: %d contacts from up to %d messages",
                    len(contacts), self.max_messages)
        return contacts
