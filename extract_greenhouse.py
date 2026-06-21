"""Extract Greenhouse fintech Data/AI roles into the Google Sheets tracker.

Runs the Greenhouse source through the normal pipeline (exclude -> score -> tier ->
store + upsert to Sheets). Greenhouse roles land as Tier A (see routing.TIER_A_SOURCES).

    python extract_greenhouse.py            # all geos, <=90 days
Env: GOOGLE_SERVICE_ACCOUNT_JSON + SPREADSHEET_ID (+ GREENHOUSE_LOCATION to filter).
"""
from __future__ import annotations

import json
import logging
import os

from runner import run
from sources.greenhouse import GreenhouseSource
from store.google_sheets_repo import GoogleSheetsRepository
from store.repository import SqliteRepository

logger = logging.getLogger("extract_greenhouse")


def _sheets() -> GoogleSheetsRepository:
    sa = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    if os.path.exists(sa):
        return GoogleSheetsRepository.from_service_account_file(sa, spreadsheet_id)
    return GoogleSheetsRepository.from_service_account_info(json.loads(sa), spreadsheet_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    loc = os.environ.get("GREENHOUSE_LOCATION") or None  # unset/empty = all geos
    raws = GreenhouseSource(location_contains=loc, max_age_days=90).fetch()
    logger.info("Fetched %d Greenhouse roles (location=%s)", len(raws), loc or "ALL")

    counts = run(
        repo=SqliteRepository(),
        jobs=raws,
        tracker=_sheets(),
        base_summary=os.environ.get("RESUME_SUMMARY", ""),
    )
    print(counts)


if __name__ == "__main__":
    main()
