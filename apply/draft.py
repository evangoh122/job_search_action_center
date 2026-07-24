from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from models import ApplicationDraft

logger = logging.getLogger(__name__)


class ApplicationDraftQueue:
    """Appends drafted (Tier B) applications to a JSONL review queue the user approves."""

    def __init__(self, path: str = "data/application_drafts.jsonl"):
        """Configure the ignored JSONL application-draft queue."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, draft: ApplicationDraft) -> str:
        """Append one application draft and return its generated identifier."""
        draft_id = str(uuid.uuid4())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": draft_id, **draft.model_dump()}) + "\n")
        logger.info("Queued application draft for %s @ %s", draft.title, draft.company)
        return draft_id
