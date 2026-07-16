from __future__ import annotations

import json

from models import Job
from network.json_feed import JsonFeedNotifier


def _job(title="Head of Data", company="DBS", url="https://x/1", score=88.0) -> Job:
    """Provide a test helper for job."""
    return Job(id="j", source="greenhouse", company_canonical=company,
               dedupe_key=f"{company}|{title}", title=title, url=url, score=score, tier="A")


def test_writes_feed(tmp_path):
    """Verify writing feed."""
    path = tmp_path / "feed.json"
    n = JsonFeedNotifier(str(path)).send_new_jobs([_job(), _job(title="VP Data", url="https://x/2")])
    assert n == 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["new_this_run"] == 2
    assert {r["title"] for r in doc["roles"]} == {"Head of Data", "VP Data"}
    r = doc["roles"][0]
    assert set(r) >= {"title", "company", "score", "url", "source", "first_seen"}


def test_empty_writes_nothing(tmp_path):
    """Verify the empty writes nothing scenario."""
    path = tmp_path / "feed.json"
    assert JsonFeedNotifier(str(path)).send_new_jobs([]) == 0
    assert not path.exists()


def test_merges_and_dedupes_across_runs(tmp_path):
    """Verify merging and dedupes across runs."""
    path = tmp_path / "feed.json"
    feed = JsonFeedNotifier(str(path))
    feed.send_new_jobs([_job(title="A", url="https://x/a")])
    feed.send_new_jobs([_job(title="B", url="https://x/b"),
                        _job(title="A-updated", url="https://x/a")])  # same url as run 1
    roles = json.loads(path.read_text(encoding="utf-8"))["roles"]
    urls = [r["url"] for r in roles]
    assert urls.count("https://x/a") == 1          # deduped by url
    assert {"https://x/a", "https://x/b"} == set(urls)
    titles = {r["title"] for r in roles}
    assert "A-updated" in titles                   # newer entry wins


def test_caps_entries(tmp_path):
    """Verify the caps entries scenario."""
    path = tmp_path / "feed.json"
    feed = JsonFeedNotifier(str(path), max_entries=5)
    feed.send_new_jobs([_job(title=f"R{i}", url=f"https://x/{i}") for i in range(20)])
    assert len(json.loads(path.read_text(encoding="utf-8"))["roles"]) == 5
