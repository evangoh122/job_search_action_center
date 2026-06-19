from __future__ import annotations

import pytest

from apply.auto_apply import AutoApplier
from models import Applicant, Job


@pytest.fixture
def applicant() -> Applicant:
    return Applicant(
        name="Alice Smith",
        email="alice@example.com",
        phone="+11234567890",
        resume_url="https://example.com/alice.pdf",
        linkedin_url="https://linkedin.com/in/alicesmith",
    )


def _job(ats: str, url: str) -> Job:
    return Job(id="j", source="test", company_canonical="Acme", dedupe_key=f"k-{ats}",
               title="Engineer", url=url, ats_type=ats)


class RecordingHTTP:
    def __init__(self, response: dict | None = None, exc: Exception | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self._response = response if response is not None else {}
        self._exc = exc

    def __call__(self, method: str, url: str, body: dict | None) -> dict:
        self.calls.append((method, url, body))
        if self._exc:
            raise self._exc
        return self._response


def test_dry_run_default_true_makes_no_call(applicant):
    http = RecordingHTTP()
    applier = AutoApplier(applicant=applicant, http=http)
    assert applier.dry_run is True
    assert applier.apply(_job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")) == "dry_run"
    assert http.calls == []


def test_submitted_greenhouse(applicant):
    http = RecordingHTTP(response={"status": "ok"})
    res = AutoApplier(applicant=applicant, dry_run=False, http=http).apply(
        _job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")
    )
    assert res == "submitted"
    method, url, payload = http.calls[0]
    assert method == "POST"
    assert payload["email"] == applicant.email


def test_submitted_lever(applicant):
    http = RecordingHTTP(response={"status": "ok"})
    res = AutoApplier(applicant=applicant, dry_run=False, http=http).apply(
        _job("lever", "https://jobs.lever.co/globex/456")
    )
    assert res == "submitted"
    _, _, payload = http.calls[0]
    assert payload["name"] == applicant.name
    assert isinstance(payload["urls"], list)


def test_unsupported_ats(applicant):
    http = RecordingHTTP()
    res = AutoApplier(applicant=applicant, dry_run=False, http=http).apply(
        _job("mycareersfuture", "https://x/1")
    )
    assert res == "unsupported"
    assert http.calls == []


def test_live_submit_error(applicant):
    http = RecordingHTTP(exc=ConnectionError("timeout"))
    res = AutoApplier(applicant=applicant, dry_run=False, http=http).apply(
        _job("greenhouse", "https://boards.greenhouse.io/acme/jobs/123")
    )
    assert res == "error"
