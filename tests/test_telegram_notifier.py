from __future__ import annotations

from models import Job
from network.telegram_notifier import TelegramNotifier


def _job(title="Head of Data", company="DBS", score=88.0, url="https://x/1") -> Job:
    """Provide a test helper for job."""
    return Job(id="j", source="greenhouse", company_canonical=company,
               dedupe_key=f"{company}|{title}", title=title, url=url, score=score)


def _fake():
    """Provide a test helper for fake."""
    sent: list[dict] = []

    def http(url: str, body: dict) -> dict:
        """Provide a test helper for http."""
        sent.append({"url": url, "body": body})
        return {"ok": True}

    return http, sent


def test_sends_digest_with_apply_links():
    """Verify sending digest with apply links."""
    http, sent = _fake()
    n = TelegramNotifier("tok", "123", http=http).send_new_jobs([_job(), _job(title="VP Data")])
    assert n == 2
    assert len(sent) == 1  # both fit one message
    body = sent[0]["body"]
    assert "/bottok/sendMessage" in sent[0]["url"]
    assert body["chat_id"] == "123"
    assert body["parse_mode"] == "HTML"
    assert "2 new role" in body["text"]
    assert 'href="https://x/1"' in body["text"]  # clickable apply link


def test_empty_sends_nothing():
    """Verify the empty sends nothing scenario."""
    http, sent = _fake()
    assert TelegramNotifier("t", "c", http=http).send_new_jobs([]) == 0
    assert sent == []


def test_html_escaped_to_avoid_breakage():
    """Verify the html escaped to avoid breakage scenario."""
    http, sent = _fake()
    TelegramNotifier("t", "c", http=http).send_new_jobs([_job(title="Data & AI <Lead>")])
    assert "Data &amp; AI &lt;Lead&gt;" in sent[0]["body"]["text"]


def test_long_digest_is_chunked():
    """Verify the long digest is chunked scenario."""
    http, sent = _fake()
    jobs = [_job(title=f"Role {i} " + "x" * 200, url=f"https://x/{i}") for i in range(60)]
    n = TelegramNotifier("t", "c", http=http).send_new_jobs(jobs)
    assert n == 60
    assert len(sent) > 1  # split across multiple messages under the 4096 cap
    assert all(len(s["body"]["text"]) <= 4096 for s in sent)
