from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent
_TARGETS_PATH = _BASE_DIR / "Target-list.json"

AUTO_APPLY_THRESHOLD: float = 92.0
DRAFT_FLOOR: float = 78.0
DAILY_CAPS: dict[str, int] = {
    "auto_apply": 10,
    "drafts": 25,
    "outreach": 15,
}


def load_targets(path: Path | None = None) -> dict[str, Any]:
    """Load Target-list.json and return its contents as a dict."""
    resolved = path or _TARGETS_PATH
    with resolved.open(encoding="utf-8") as f:
        return json.load(f)
