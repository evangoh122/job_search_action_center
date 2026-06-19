"""Exclusion gate — runs FIRST, before scoring or any outbound action.

Single source of truth: config/exclusions.json. Never apply, email, scrape, or
contact an excluded company (current employer + affiliates).

Matching is canonical/alias on a *normalized* name, NOT substring, to avoid
false positives like "JRI" matching "JR Industries".
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "exclusions.json"
_SUFFIXES = r"\b(inc|llc|ltd|limited|corp|corporation|co|company|group|plc|pte|sa|ag|nv)\b"


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation + common corporate suffixes, collapse whitespace."""
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(_SUFFIXES, " ", n)
    return re.sub(r"\s+", " ", n).strip()


@lru_cache(maxsize=1)
def _excluded_token_sets() -> tuple[frozenset[str], ...]:
    """One token-set per canonical/alias, loaded once from config.

    Matching is token-subset: a company is excluded if every token of any
    excluded entry appears in the company name. This catches branch variants
    ("Sumitomo Mitsui Banking Corporation, Singapore Branch") while staying
    safe against partial-word collisions ("Smbcorp Tech", "JR Industries"),
    because matching is on whole tokens, not substrings.
    """
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        # Fail CLOSED: never silently allow jobs through if the gate config is gone.
        raise RuntimeError(
            f"Exclusion config missing at {_CONFIG_PATH}; refusing to run the gate."
        ) from e
    sets = {
        frozenset(_normalize(alias).split())
        for group in ("excluded_companies", "excluded_consulting")
        for entry in data.get(group, [])
        for alias in (entry["canonical"], *entry.get("aliases", []))
    }
    sets.discard(frozenset())
    return tuple(sets)


def is_excluded_company(company_name: str) -> bool:
    """Return True if the company is the current employer or an affiliate."""
    if not company_name:
        return False
    tokens = frozenset(_normalize(company_name).split())
    if not tokens:
        return False
    for excluded in _excluded_token_sets():
        if excluded <= tokens:
            logger.warning("EXCLUDED COMPANY: %s", company_name)
            return True
    return False
