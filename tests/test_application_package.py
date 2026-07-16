from __future__ import annotations

from datetime import date

from apply.application_package import company_abbreviation, resume_filename


def test_company_abbreviation_keeps_single_company_acronym():
    """Verify the company abbreviation keeps single company acronym scenario."""
    assert company_abbreviation("DBS") == "DBS"


def test_company_abbreviation_uses_meaningful_initials():
    """Verify the company abbreviation uses meaningful initials scenario."""
    assert company_abbreviation("Bank of America") == "BA"
    assert company_abbreviation("Standard Chartered Bank") == "SCB"


def test_resume_filename_uses_mmddyyyy_and_company_abbreviation():
    """Verify the resume filename uses mmddyyyy and company abbreviation scenario."""
    assert resume_filename("Standard Chartered Bank", date(2026, 7, 12)) == (
        "Evan_Resume07122026_SCB.docx"
    )
