from __future__ import annotations

import uuid

from apply.tailor import matched_keywords, tailor
from apply.resume_models import ResumeAchievement
from models import ApplicationDraft, Job


def _job() -> Job:
    """Provide a test helper for job."""
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
    """Verify the matched keywords primary present scenario."""
    kws = matched_keywords(_job())
    assert "machine learning" in kws
    assert "data science" in kws


def test_tailor_returns_application_draft():
    """Verify the tailor returns application draft scenario."""
    draft = tailor(_job(), base_summary="5 years of experience.", applicant_name="Alice")
    assert isinstance(draft, ApplicationDraft)
    assert "Acme Corp" in draft.cover_letter
    assert "Senior Data Scientist" in draft.cover_letter
    assert "Alice" in draft.cover_letter
    assert draft.matched_keywords
    assert draft.application_link == "https://example.com/job"
    assert draft.resume_filename.startswith("Evan_Resume")
    assert draft.resume_filename.endswith("_AC.pdf")


def test_tailor_can_attach_keyword_xyz_resume_variant():
    """Verify the tailor can attach keyword xyz resume variant scenario."""
    draft = tailor(
        _job(),
        achievements=[
            ResumeAchievement(
                evidence_id="monitoring-1",
                source="master resume",
                block_text=(
                    "Improved model monitoring coverage across critical production models "
                    "by building reusable Python validation checks."
                ),
                keyword="machine learning",
                result="Improved model monitoring coverage",
                metric="coverage across critical production models",
                method="building reusable Python validation checks",
                tags=["machine learning", "python"],
            )
        ],
    )

    assert draft.resume_keywords
    assert draft.resume_bullets == [
        "Improved model monitoring coverage across critical production models "
        "by building reusable Python validation checks."
    ]
    assert "Relevant evidence includes:" in draft.cover_letter
    assert "Improved model monitoring coverage" in draft.cover_letter
    assert draft.resume_fit_brief["primary_role_family"]
    assert len(draft.resume_version_id) == 16
    assert draft.resume_evidence_ids == ["monitoring-1"]
    assert draft.resume_keyword_map
    assert draft.resume_selected_evidence
    assert draft.resume_change_log
    assert draft.resume_pagination_status.startswith("two-page-targeted")


def test_resume_version_changes_when_rendered_resume_content_changes():
    """Verify the resume version changes when rendered resume content changes scenario."""
    job = _job()
    first = ResumeAchievement(
        evidence_id="same-id", source="master resume",
        block_text="Improved coverage across 10 models using Python.",
        keyword="machine learning", result="Improved coverage",
        metric="10 models", method="using Python",
    )
    changed = ResumeAchievement(
        evidence_id="same-id", source="master resume",
        block_text="Improved coverage across 20 models using Python.",
        keyword="machine learning", result="Improved coverage",
        metric="20 models", method="using Python",
    )
    assert tailor(job, achievements=[first]).resume_version_id != tailor(
        job, achievements=[changed]
    ).resume_version_id
