from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent
_TARGETS_PATH = _BASE_DIR / "Target-list.json"

# Calibrated to the TF-IDF + ATS scoring distribution (see scoring.py). The cosine-based
# match compresses scores (a strong target-bank role lands ~60-67), so these are lower than
# a raw keyword-count formula would use. Outreach creates Gmail drafts only and auto-apply
# is dry-run by default, so these gate drafting, not live sends.
AUTO_APPLY_THRESHOLD: float = 65.0
DRAFT_FLOOR: float = 55.0
DAILY_CAPS: dict[str, int] = {
    "auto_apply": 10,
    "drafts": 25,
    "outreach": 15,
}


def load_targets(path: Path | None = None) -> dict[str, Any]:
    """Load Target-list.json and return its contents as a dict."""
    candidates = [path] if path is not None else [_TARGETS_PATH, Path(sys.prefix) / "Target-list.json"]
    for resolved in candidates:
        if resolved is not None and resolved.is_file():
            with resolved.open(encoding="utf-8") as f:
                return json.load(f)
    searched = ", ".join(str(candidate) for candidate in candidates if candidate is not None)
    raise FileNotFoundError(f"Target-list.json was not found in: {searched}")


_SALARY_RULES = load_targets()["salary_rules"]
MINIMUM_MONTHLY_SGD: float = float(_SALARY_RULES["minimum_monthly_sgd"])
