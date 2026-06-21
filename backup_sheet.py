"""Daily backup: snapshot every tab of the tracker spreadsheet into date-stamped tabs
in a SEPARATE backup spreadsheet. Runs via GitHub Actions, or locally:

    python backup_sheet.py

Needs GOOGLE_SERVICE_ACCOUNT_JSON + SPREADSHEET_ID (source) and BACKUP_SPREADSHEET_ID
(destination). The backup spreadsheet must already exist and be shared with the
service account. Re-running the same day overwrites that day's snapshot tabs.
"""
from __future__ import annotations

import json
import logging
import os

from store.google_sheets_repo import GoogleSheetsRepository

logger = logging.getLogger("backup_sheet")


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

    backup_id = os.environ["BACKUP_SPREADSHEET_ID"]
    written = _sheets().snapshot_to(backup_id)
    logger.info("Backed up %d tabs: %s", len(written), written)
    print(f"backed_up_tabs={len(written)}")


if __name__ == "__main__":
    main()
