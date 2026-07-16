"""One-time helper: complete Gmail OAuth consent and print a refresh token.

Prereqs:
  pip install google-auth-oauthlib
  .env must have GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET (Desktop OAuth client).

Run:
  python scripts/get_gmail_refresh_token.py

It opens a browser, you approve the `gmail.compose` scope with the Google account you want
to send from, then it prints a refresh token. Paste that into .env as GMAIL_REFRESH_TOKEN.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# gmail.compose = create drafts / send; CANNOT read your inbox (least privilege).
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main() -> None:
    """Run local OAuth consent and print the resulting Gmail refresh token."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("Missing dependency. Run: pip install google-auth-oauthlib")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")  # forces a refresh_token

    if not creds.refresh_token:
        sys.exit("No refresh token returned. Revoke prior access and re-run with prompt=consent.")

    print("\n" + "=" * 60)
    print("SUCCESS — paste this into .env as GMAIL_REFRESH_TOKEN:\n")
    print(creds.refresh_token)
    print("=" * 60)


if __name__ == "__main__":
    main()
