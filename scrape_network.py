"""Scrape networking contacts from Gmail (last 12 months) into the orange
"Networking Tracker" tab. Runs daily via GitHub Actions, or locally:

    python scrape_network.py

Needs Gmail OAuth (gmail.readonly scope) via GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET /
GMAIL_REFRESH_TOKEN, plus the Google Sheets tracker creds (GOOGLE_SERVICE_ACCOUNT_JSON
+ SPREADSHEET_ID). APPLICANT_EMAIL is used to tell inbound from outbound mail.
"""
from __future__ import annotations

import json
import logging
import os

from network.gmail_network import GmailNetworkScraper
from store.google_sheets_repo import GoogleSheetsRepository

logger = logging.getLogger("scrape_network")


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

    scraper = GmailNetworkScraper.from_refresh_token(
        os.environ["GMAIL_CLIENT_ID"],
        os.environ["GMAIL_CLIENT_SECRET"],
        os.environ["GMAIL_REFRESH_TOKEN"],
        user_email=os.environ.get("APPLICANT_EMAIL", ""),
    )
    sheets = _sheets()
    contacts = scraper.scrape("newer_than:1y -in:chats")
    for c in contacts:
        sheets.upsert_networking(
            name=c.name, email=c.email, company=c.company,
            source=c.source, last_contacted=c.last_contacted,
        )
    logger.info("Wrote %d networking contacts to the Networking Tracker tab.", len(contacts))
    print(f"networking_contacts={len(contacts)}")


if __name__ == "__main__":
    main()
