"""Tier A gated auto-apply. Submits to REAL employers — `dry_run` defaults True; a live submit
only happens when dry_run=False AND routing already gated on score>=92 + simple ATS + allowlist.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from apply.ats import ADAPTERS
from models import Applicant, Job

logger = logging.getLogger(__name__)

HttpFn = Callable[[str, str, dict | None], dict]


class AutoApplier:
    def __init__(self, applicant: Applicant, dry_run: bool = True, http: HttpFn | None = None):
        self.applicant = applicant
        self.dry_run = dry_run
        self.http = http or self._default_http

    def _default_http(self, method: str, url: str, body: dict | None) -> dict:
        r = httpx.request(method, url, json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def apply(self, job: Job) -> str:
        """Returns 'unsupported' | 'dry_run' | 'submitted' | 'error'."""
        builder = ADAPTERS.get((job.ats_type or "").lower())
        if builder is None:
            logger.info("No ATS adapter for %s (%s)", job.ats_type, job.title)
            return "unsupported"
        url, payload = builder(job, self.applicant)
        if self.dry_run:
            logger.info("[DRY_RUN] would auto-apply to %s at %s", job.title, url)
            return "dry_run"
        if not self.applicant.email:
            logger.warning("No applicant email — refusing live auto-apply for %s", job.title)
            return "error"
        try:
            self.http("POST", url, payload)
            logger.info("Auto-applied to %s at %s", job.title, url)
            return "submitted"
        except Exception:
            logger.warning("Auto-apply failed for %s", job.title, exc_info=True)
            return "error"
