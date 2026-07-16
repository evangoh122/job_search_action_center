from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from models import Contact
from network.email_finder import _classify

logger = logging.getLogger(__name__)

HttpPost = Callable[[str, dict], list]  # (url, json_body) -> list of items

_ACTOR = "bebity~linkedin-jobs-scraper"
_RUN_URL = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"


class LinkedInPosterFinder:
    """Finds the specific person who posted a role on LinkedIn (hiring manager / recruiter),
    via an Apify LinkedIn Jobs actor. Injectable HTTP; needs APIFY_TOKEN for live use.
    LinkedIn exposes no email — enrich via Hunter, or the user messages them on LinkedIn.

    Note: scraping LinkedIn is ToS-sensitive and Apify actors bill in credits — this runs
    only when the user opts in by setting APIFY_TOKEN. Read-only, one lookup per qualified job.
    """

    def __init__(self, token: str, http_post: HttpPost | None = None):
        """Configure Apify authentication and an injectable request function."""
        self.token = token
        self.http_post = http_post or self._default_post

    def _default_post(self, url: str, body: dict) -> list:
        """Run the Apify actor with bearer authentication outside the URL."""
        r = httpx.post(
            url, headers={"Authorization": f"Bearer {self.token}"},
            json=body, timeout=180,
        )  # Apify run-sync can be slow
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _items(resp) -> list:
        """run-sync-get-dataset-items returns an array, but tolerate a wrapped dict too."""
        if isinstance(resp, dict):
            return resp.get("items") or resp.get("data") or []
        return resp or []

    def find_poster(self, job_url: str, company: str = "") -> Contact | None:
        """Return the first credible poster associated with a LinkedIn vacancy."""
        url = _RUN_URL
        try:
            items = self._items(self.http_post(url, {"urls": [job_url]}))
        except Exception:
            logger.warning("LinkedIn poster lookup failed for %s", job_url, exc_info=True)
            return None

        for item in items:
            name = item.get("jobPosterName")
            if not name:
                continue
            title = item.get("jobPosterTitle", "") or ""
            profile = item.get("jobPosterProfileUrl", "") or ""
            rt = _classify(title, "") or "hiring_manager"  # default unknown posters to HM
            return Contact(
                id=profile or name,
                name=name,
                company_canonical=company or item.get("companyName", ""),
                role=title,
                role_type=rt,
                linkedin_url=profile,
                email="",
            )
        return None
