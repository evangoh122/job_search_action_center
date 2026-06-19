"""Outreach track: Gmail drafter, review-queue fallback, runner cap enforcement."""
from __future__ import annotations

from datetime import datetime

from config import DAILY_CAPS
from models import Contact, EmailDraft, Job
from network.gmail_drafter import (
    GmailDrafter,
    ReviewQueueDrafter,
    refresh_gmail_access_token,
)
from store.repository import SqliteRepository
import runner


def _draft() -> EmailDraft:
    return EmailDraft(
        job_id="j1", company="Acme", to_email="x@acme.com", to_name="X",
        role_type="recruiter", subject="Hi", body="Body",
    )


def test_gmail_drafter_posts_to_drafts_endpoint():
    calls: list[tuple[str, str, dict | None]] = []

    def http(method, url, body):
        calls.append((method, url, body))
        return {"id": "draft-123"}

    out = GmailDrafter(token="t", http=http).create_draft(_draft())
    assert out == "draft-123"
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/users/me/drafts")
    assert "raw" in calls[0][2]["message"]


def test_review_queue_drafter_writes_jsonl(tmp_path):
    path = tmp_path / "drafts.jsonl"
    did = ReviewQueueDrafter(str(path)).create_draft(_draft())
    assert did
    assert "x@acme.com" in path.read_text(encoding="utf-8")


def test_refresh_gmail_access_token():
    def token_post(url, data):
        assert url.endswith("/token")
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "r-token"
        assert data["client_id"] == "cid"
        return {"access_token": "ya29.fresh"}

    assert refresh_gmail_access_token("cid", "secret", "r-token", token_post=token_post) == "ya29.fresh"


def test_gmail_drafter_caches_access_token():
    calls = []

    def token_post(url, data):
        calls.append(data)
        return {"access_token": "ya29.fresh"}

    d = GmailDrafter.from_refresh_token("cid", "secret", "r-token", token_post=token_post)
    assert d._access_token() == "ya29.fresh"
    assert d._access_token() == "ya29.fresh"
    assert len(calls) == 1  # refresh happens once, then cached for the run


def test_gmail_drafter_from_refresh_token_creates_draft():
    def token_post(url, data):
        return {"access_token": "ya29.fresh"}

    http_calls = []

    def http(method, url, body):
        http_calls.append((method, url, body))
        return {"id": "draft-oauth"}

    d = GmailDrafter.from_refresh_token("cid", "secret", "r", http=http, token_post=token_post)
    assert d.create_draft(_draft()) == "draft-oauth"
    assert http_calls[0][1].endswith("/users/me/drafts")


class _FakeFinder:
    def find_people(self, company, max_each=1):
        return [
            Contact(id="r", name="Rec", company_canonical=company, role_type="recruiter", email="r@x.com"),
            Contact(id="m", name="Mgr", company_canonical=company, role_type="hiring_manager", email="m@x.com"),
        ]


class _CountingDrafter:
    def __init__(self):
        self.n = 0

    def create_draft(self, draft):
        self.n += 1
        return str(self.n)


def _qualified_job() -> Job:
    return Job(id="j1", source="t", company_canonical="Databricks",
               dedupe_key="k", title="Senior Data Scientist", url="https://x.com/1", score=90.0)


def test_outreach_creates_two_drafts():
    repo = SqliteRepository()
    drafter = _CountingDrafter()
    day = datetime.now().date().isoformat()
    n = runner._run_outreach(_qualified_job(), repo, _FakeFinder(), drafter, "", day)
    assert n == 2  # recruiter + hiring manager
    assert drafter.n == 2


def test_outreach_respects_daily_cap():
    repo = SqliteRepository()
    day = datetime.now().date().isoformat()
    for _ in range(DAILY_CAPS["outreach"]):
        repo.incr_action("outreach", day)  # already at cap
    n = runner._run_outreach(_qualified_job(), repo, _FakeFinder(), _CountingDrafter(), "", day)
    assert n == 0


def test_outreach_disabled_without_finder():
    repo = SqliteRepository()
    day = datetime.now().date().isoformat()
    assert runner._run_outreach(_qualified_job(), repo, None, None, "", day) == 0
