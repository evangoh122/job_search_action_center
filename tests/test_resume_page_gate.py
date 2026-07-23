from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyPDF2 import PdfWriter

requires_pdftoppm = pytest.mark.skipif(
    shutil.which("pdftoppm") is None,
    reason="poppler-utils (pdftoppm) not installed; required for visual QA previews",
)

from resume_page_gate import (
    ResumePaginationError,
    inspect_resume_pages,
    record_visual_qa,
    render_visual_qa_previews,
    require_two_page_resume,
    require_visual_qa,
)


def _pdf(path, pages: int):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)
    return path


@pytest.mark.parametrize("pages", [1, 3])
def test_resume_page_gate_blocks_anything_not_exactly_two_pages(tmp_path, pages):
    resume = _pdf(tmp_path / f"resume-{pages}.pdf", pages)
    report = inspect_resume_pages(resume)
    assert report.page_count == pages
    assert not report.passed
    with pytest.raises(ResumePaginationError, match="exactly 2 pages"):
        require_two_page_resume(resume)


def test_resume_page_gate_accepts_exactly_two_rendered_pages(tmp_path):
    resume = _pdf(tmp_path / "resume-2.pdf", 2)
    report = require_two_page_resume(resume)
    assert report.passed
    assert report.page_count == 2


def test_resume_page_gate_rejects_unreadable_pdf(tmp_path):
    resume = tmp_path / "broken.pdf"
    resume.write_bytes(b"not a PDF")
    with pytest.raises(ResumePaginationError, match="could not read"):
        require_two_page_resume(resume)


@requires_pdftoppm
def test_visual_qa_receipt_is_bound_to_exact_pdf_bytes(tmp_path):
    resume = _pdf(tmp_path / "resume.pdf", 2)
    root = tmp_path / "visual"
    receipt = record_visual_qa(
        resume, reviewer="Alice", confirmed=True, root=root,
    )
    assert require_visual_qa(resume, root).receipt_id == receipt.receipt_id
    resume.write_bytes(b"changed")
    with pytest.raises(ResumePaginationError, match="visual QA receipt"):
        require_visual_qa(resume, root)


@requires_pdftoppm
def test_visual_qa_rejects_missing_or_changed_previews(tmp_path):
    resume = _pdf(tmp_path / "resume.pdf", 2)
    root = tmp_path / "visual"
    unrelated = [tmp_path / "page-1.png", tmp_path / "page-2.png"]
    for index, preview in enumerate(unrelated):
        preview.write_bytes(f"unrelated {index}".encode())
    with pytest.raises(ResumePaginationError, match="not exact renders"):
        record_visual_qa(
            resume, reviewer="Alice", confirmed=True, root=root,
            existing_preview_paths=[str(item) for item in unrelated],
        )
    receipt = record_visual_qa(resume, reviewer="Alice", confirmed=True, root=root)
    Path(receipt.preview_paths[0]).write_bytes(b"tampered preview")
    with pytest.raises(ResumePaginationError, match="preview bytes changed"):
        require_visual_qa(resume, root)


@requires_pdftoppm
def test_visual_qa_receipts_are_append_only_versions(tmp_path):
    resume = _pdf(tmp_path / "resume.pdf", 2)
    root = tmp_path / "visual"
    first = record_visual_qa(resume, reviewer="Alice", confirmed=True, root=root)
    second = record_visual_qa(resume, reviewer="Bob", confirmed=True, root=root)
    receipts = list((root / first.resume_hash / "receipts").glob("*.json"))
    assert first.receipt_id != second.receipt_id
    assert len(receipts) == 2
    assert require_visual_qa(
        resume, receipt_path=next(item for item in receipts if first.receipt_id in item.name)
    ).receipt_id == first.receipt_id


@requires_pdftoppm
def test_visual_qa_accepts_only_the_exact_previews_shown_to_reviewer(tmp_path):
    resume = _pdf(tmp_path / "resume.pdf", 2)
    shown = render_visual_qa_previews(resume, tmp_path / "shown")
    receipt = record_visual_qa(
        resume, reviewer="Alice", confirmed=True, root=tmp_path / "visual",
        existing_preview_paths=[str(item) for item in shown],
    )
    assert len(receipt.preview_hashes) == 2
