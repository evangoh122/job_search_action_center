"""Read-only export of the whole Airtable base to a local JSON file.

Only needs AIRTABLE_TOKEN / AIRTABLE_BASE_ID (+ table-name env vars) — no Google creds.
Useful as a raw backup and as the source for migrate_airtable_to_sheets.py once Sheets
credentials are in place.

    python extract_airtable.py            # -> airtable_export.json
"""
from __future__ import annotations

import json
import os

from migrate_airtable_to_sheets import _fetch_all

OUT_PATH = "airtable_export.json"


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    token = os.environ["AIRTABLE_TOKEN"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    tables = {
        "jobs": os.environ.get("AIRTABLE_JOBS_TABLE", "Jobs"),
        "contacts": os.environ.get("AIRTABLE_CONTACTS_TABLE", "Contacts"),
        "outreach": os.environ.get("AIRTABLE_OUTREACH_TABLE", "Outreach"),
    }

    export: dict[str, list[dict]] = {}
    for kind, table in tables.items():
        records = _fetch_all(token, base_id, table)
        export[kind] = records
        print(f"{kind} ({table}): {len(records)} records")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
