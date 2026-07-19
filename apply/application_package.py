from __future__ import annotations

import re
from datetime import date

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_FILLER = {"and", "of", "the", "for", "to", "in", "at", "a", "an"}


def company_abbreviation(company: str) -> str:
    """Create a compact company abbreviation for application package filenames."""
    tokens = [t for t in _NON_ALNUM.split(company.strip()) if t]
    if not tokens:
        return "COMPANY"
    if len(tokens) == 1:
        return tokens[0].upper()
    meaningful = [t for t in tokens if t.lower() not in _FILLER] or tokens
    return "".join(t[0].upper() for t in meaningful)


def resume_filename(company: str, today: date | None = None, extension: str = "pdf") -> str:
    """Return the deterministic PDF-only application résumé filename."""
    day = today or date.today()
    normalized = extension.lstrip(".").casefold()
    if normalized != "pdf":
        raise ValueError("application résumé filenames are PDF-only")
    suffix = ".pdf"
    return f"Evan_Resume{day:%m%d%Y}_{company_abbreviation(company)}{suffix}"
