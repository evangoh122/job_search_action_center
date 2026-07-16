from __future__ import annotations

from network.gmail_network import (
    GmailNetworkScraper,
    _company_from_email,
    _is_automated,
    _parse_date,
)


def _fake(messages: dict[str, dict]):
    """messages: msg_id -> {From,To,Cc,Date} header dict. List returns them all."""
    calls: list[str] = []

    def http(method: str, url: str, body: dict | None) -> dict:
        """Provide a test helper for http."""
        calls.append(url)
        if "/messages/" in url:  # single-message metadata
            msg_id = url.split("/messages/")[1].split("?")[0]
            hdrs = messages[msg_id]
            return {"payload": {"headers": [{"name": k, "value": v} for k, v in hdrs.items()]}}
        return {"messages": [{"id": mid} for mid in messages]}  # list

    return http, calls


def test_received_extracts_sender():
    """Verify the received extracts sender scenario."""
    msgs = {"m1": {"From": "Jane Tan <jane@dbs.com>", "To": "me@x.com", "Date": "Mon, 1 Jun 2026 10:00:00 +0800"}}
    scraper = GmailNetworkScraper(token="t", user_email="me@x.com", http=_fake(msgs)[0])
    contacts = scraper.scrape()
    assert len(contacts) == 1
    c = contacts[0]
    assert c.email == "jane@dbs.com"
    assert c.name == "Jane Tan"
    assert c.company == "Dbs"
    assert c.last_contacted == "2026-06-01"
    assert c.source == "gmail:received"


def test_sent_extracts_recipients_not_self():
    """Verify the sent extracts recipients not self scenario."""
    msgs = {"m1": {"From": "me@x.com", "To": "Sam Lee <sam@acme.com>, me@x.com",
                   "Cc": "ria@acme.com", "Date": "Tue, 2 Jun 2026 09:00:00 +0000"}}
    scraper = GmailNetworkScraper(token="t", user_email="me@x.com", http=_fake(msgs)[0])
    emails = {c.email for c in scraper.scrape()}
    assert emails == {"sam@acme.com", "ria@acme.com"}  # self filtered out


def test_automated_senders_skipped():
    """Verify the automated senders skipped scenario."""
    msgs = {
        "m1": {"From": "no-reply@linkedin.com", "Date": "Wed, 3 Jun 2026 09:00:00 +0000"},
        "m2": {"From": "Recruiter <ana@bank.com>", "Date": "Wed, 3 Jun 2026 09:00:00 +0000"},
    }
    scraper = GmailNetworkScraper(token="t", user_email="me@x.com", http=_fake(msgs)[0])
    emails = {c.email for c in scraper.scrape()}
    assert emails == {"ana@bank.com"}


def test_dedupe_keeps_most_recent_and_backfills_name():
    """Verify the dedupe keeps most recent and backfills name scenario."""
    msgs = {
        "m1": {"From": "jane@dbs.com", "Date": "Mon, 1 Jun 2026 10:00:00 +0000"},          # no name, older
        "m2": {"From": "Jane Tan <jane@dbs.com>", "Date": "Fri, 5 Jun 2026 10:00:00 +0000"},  # name, newer
    }
    scraper = GmailNetworkScraper(token="t", user_email="me@x.com", http=_fake(msgs)[0])
    contacts = scraper.scrape()
    assert len(contacts) == 1
    assert contacts[0].name == "Jane Tan"
    assert contacts[0].last_contacted == "2026-06-05"


def test_query_passed_through_and_capped():
    """Verify the query passed through and capped scenario."""
    msgs = {f"m{i}": {"From": f"p{i}@acme.com", "Date": "Mon, 1 Jun 2026 10:00:00 +0000"}
            for i in range(5)}
    http, calls = _fake(msgs)
    scraper = GmailNetworkScraper(token="t", user_email="me@x.com", http=http, max_messages=3)
    contacts = scraper.scrape(query="newer_than:1y -in:chats")
    assert len(contacts) == 3  # capped
    list_call = calls[0]
    assert "newer_than%3A1y" in list_call  # query url-encoded into the list request


def test_helpers():
    """Verify the helpers scenario."""
    assert _is_automated("", "noreply@x.com")
    assert not _is_automated("Jane", "jane@dbs.com")
    assert _company_from_email("a@gmail.com") == ""          # free provider
    assert _company_from_email("a@standardchartered.com") == "Standardchartered"
    assert _parse_date(None) == ""
    assert _parse_date("Mon, 1 Jun 2026 10:00:00 +0000") == "2026-06-01"
