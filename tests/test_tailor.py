from __future__ import annotations

import uuid

from apply.tailor import matched_keywords, tailor
from models import ApplicationDraft, Job


def _job() -> Job:
    return Job(
        id=str(uuid.uuid4()),
        source="test",
        company_canonical="Acme Corp",
        dedupe_key="acme-senior-ds",
        title="Senior Data Scientist",
        url="https://example.com/job",
        description="machine learning and data science with python",
    )


def test_matched_keywords_primary_present():
    kws = matched_keywords(_job())
    assert "machine learning" in kws
    assert "data science" in kws


def test_tailor_returns_application_draft():
    draft = tailor(_job(), base_summary="5 years of experience.", applicant_name="Alice")
    assert isinstance(draft, ApplicationDraft)
    assert "Acme Corp" in draft.cover_letter
    assert "Senior Data Scientist" in draft.cover_letter
    assert "Alice" in draft.cover_letter
    assert draft.matched_keywords
