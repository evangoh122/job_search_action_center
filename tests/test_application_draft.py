from __future__ import annotations

import json
import uuid
from pathlib import Path

from apply.draft import ApplicationDraftQueue
from models import ApplicationDraft


def test_add_creates_jsonl_with_draft(tmp_path: Path):
    queue = ApplicationDraftQueue(str(tmp_path / "q.jsonl"))
    draft = ApplicationDraft(
        job_id=str(uuid.uuid4()),
        company="Acme Corp",
        title="Data Engineer",
        url="https://example.com",
        cover_letter="Hello!",
        matched_keywords=["python", "spark"],
    )
    draft_id = queue.add(draft)
    assert draft_id
    record = json.loads((tmp_path / "q.jsonl").read_text(encoding="utf-8").strip())
    assert record["company"] == "Acme Corp"
    assert record["id"] == draft_id
