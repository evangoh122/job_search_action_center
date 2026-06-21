"""Notify allowlist — new-role notifications fire ONLY for these companies.

Source of truth: Notify-list.json (overridable with NOTIFY_COMPANIES, a comma-separated
list). Matching reuses the exclusion gate's token-subset logic on a normalized name, so
"DBS" matches "DBS Bank" and "JPMorgan" matches "JPMorgan Chase" without substring
false-positives. An empty list means notify for all companies.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from exclusions import _normalize

_PATH = Path(__file__).resolve().parent / "Notify-list.json"


@lru_cache(maxsize=1)
def _notify_token_sets() -> tuple[frozenset[str], ...]:
    env = os.environ.get("NOTIFY_COMPANIES")
    if env is not None:
        names = [n for n in env.split(",")]
    else:
        try:
            names = json.loads(_PATH.read_text(encoding="utf-8")).get("companies", [])
        except (FileNotFoundError, ValueError):
            names = []
    sets = {frozenset(_normalize(n).split()) for n in names}
    sets.discard(frozenset())
    return tuple(sets)


def notify_company_match(company: str) -> bool:
    """True if the company is on the notify allowlist (or the list is empty)."""
    sets = _notify_token_sets()
    if not sets:
        return True  # no allowlist configured -> notify everything
    tokens = frozenset(_normalize(company or "").split())
    return any(entry <= tokens for entry in sets if tokens)
