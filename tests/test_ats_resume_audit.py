from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import apply.ats_resume_audit as audit_module
from apply.ats_resume_audit import audit_docx

_PREFIX = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body>'
)
_SUFFIX = "</w:body></w:document>"


def _docx(tmp_path: Path, body: str, *, header: bool = False) -> Path:
    """Provide a test helper for docx."""
    path = tmp_path / "resume.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f"{_PREFIX}{body}{_SUFFIX}")
        if header:
            archive.writestr("word/header1.xml", "<header />")
    return path


def _paragraph(text: str) -> str:
    """Provide a test helper for paragraph."""
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def test_audit_docx_reports_sections_and_transparent_keyword_coverage(tmp_path: Path):
    """Verify the audit docx reports sections and transparent keyword coverage scenario."""
    body = "".join(
        _paragraph(text)
        for text in (
            "Professional Summary",
            "Data leader with Python and machine learning experience",
            "Professional Experience",
            "Technical Skills",
            "Education",
        )
    )

    audit = audit_docx(_docx(tmp_path, body), ["Python", "machine learning", "SQL"])

    assert audit.text_extraction_succeeded
    assert audit.recognized_sections == ["summary", "experience", "skills", "education"]
    assert audit.matched_keywords == ["python", "machine learning"]
    assert audit.missing_keywords == ["sql"]
    assert audit.keyword_coverage == pytest.approx(2 / 3, abs=0.001)
    assert audit.issues == []


def test_audit_docx_flags_common_parser_risks(tmp_path: Path):
    """Verify the audit docx flags common parser risks scenario."""
    body = (
        _paragraph("Summary")
        + "<w:tbl><w:tr><w:tc>" + _paragraph("Experience in a table") + "</w:tc></w:tr></w:tbl>"
        + "<w:txbxContent>" + _paragraph("Text box") + "</w:txbxContent>"
        + '<w:sectPr><w:cols w:num="2"/></w:sectPr>'
    )

    audit = audit_docx(_docx(tmp_path, body, header=True))

    assert audit.has_tables
    assert audit.has_text_boxes
    assert audit.has_multiple_columns
    assert audit.has_headers_or_footers
    assert len(audit.issues) >= 7


def test_audit_rejects_unsupported_file_type(tmp_path: Path):
    """Verify the audit rejects unsupported file type scenario."""
    with pytest.raises(ValueError, match="supports .docx"):
        audit_docx(tmp_path / "resume.pdf")


def test_audit_preserves_word_line_breaks(tmp_path: Path):
    """Verify the audit preserves word line breaks scenario."""
    body = (
        "<w:p><w:r><w:t>Professional Experience</w:t><w:br/>"
        "<w:t>Technical Skills</w:t></w:r></w:p>"
        + _paragraph("Education")
    )

    audit = audit_docx(_docx(tmp_path, body), ["experience technical"])

    assert audit.missing_keywords == ["experience technical"]


def test_audit_reports_corrupt_docx_clearly(tmp_path: Path):
    """Verify the audit reports corrupt docx clearly scenario."""
    path = tmp_path / "corrupt.docx"
    path.write_bytes(b"not a zip archive")

    with pytest.raises(ValueError, match="corrupt or encrypted"):
        audit_docx(path)


def test_audit_rejects_oversized_document_xml_before_reading(tmp_path: Path, monkeypatch):
    """Verify the audit rejects oversized document xml before reading scenario."""
    monkeypatch.setattr(audit_module, "_MAX_DOCUMENT_XML_BYTES", 32)
    path = _docx(tmp_path, _paragraph("Professional Experience"))
    with pytest.raises(ValueError, match="safety limit"):
        audit_docx(path)


def test_audit_uses_hardened_xml_parser(tmp_path: Path):
    """Verify the audit uses hardened xml parser scenario."""
    body = '<!DOCTYPE x [<!ENTITY boom "unsafe">]><w:p><w:r><w:t>&boom;</w:t></w:r></w:p>'
    with pytest.raises(ValueError, match="corrupt or encrypted"):
        audit_docx(_docx(tmp_path, body))
