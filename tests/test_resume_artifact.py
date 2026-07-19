from __future__ import annotations

import pytest
from PyPDF2 import PdfWriter

from apply.resume_artifact import (
    FinalResumeArtifactError,
    require_final_resume_pdf,
    stage_approved_resume_pdf,
)


def _pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)
    return path


def test_final_resume_gate_accepts_pdf_name_and_signature(tmp_path):
    resume = _pdf(tmp_path / "resume.pdf")
    assert require_final_resume_pdf(resume) == resume.resolve()


def test_final_resume_gate_rejects_valid_pdf_with_docx_extension(tmp_path):
    resume = _pdf(tmp_path / "resume.docx")
    with pytest.raises(FinalResumeArtifactError, match="must be a .pdf"):
        require_final_resume_pdf(resume)


@pytest.mark.parametrize("content", [b"PK fake docx", b"%PDF-1.7\n"])
def test_final_resume_gate_rejects_renamed_or_fake_pdf_bytes(tmp_path, content):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(content)
    with pytest.raises(FinalResumeArtifactError):
        require_final_resume_pdf(resume)


def test_staged_upload_bytes_must_match_approved_sha256(tmp_path):
    import hashlib
    resume = _pdf(tmp_path / "resume.pdf")
    approved_hash = hashlib.sha256(resume.read_bytes()).hexdigest()
    _pdf(resume)  # replace the path with another structurally valid PDF
    resume.write_bytes(resume.read_bytes() + b"changed")
    with pytest.raises(FinalResumeArtifactError, match="changed after approval"):
        with stage_approved_resume_pdf(resume, approved_hash):
            pass
