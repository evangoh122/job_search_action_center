"""Fail-closed rendered page-count gate for application résumé artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from PyPDF2 import PdfReader


REQUIRED_RESUME_PAGES = 2


class ResumePaginationError(ValueError):
    """Raised when the final rendered résumé cannot be proven to be exactly two pages."""


class ResumePageReport(BaseModel):
    source_path: str
    rendered_path: str
    page_count: int
    required_pages: int = REQUIRED_RESUME_PAGES
    passed: bool


class ResumeVisualQAReceipt(BaseModel):
    receipt_id: str
    resume_hash: str
    page_count: int
    reviewer: str
    reviewed_at: str
    preview_paths: list[str]
    preview_hashes: list[str]


def _visual_receipt_id(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _soffice_path() -> str | None:
    discovered = shutil.which("soffice") or shutil.which("libreoffice")
    if discovered:
        return discovered
    candidates = (
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _render_docx_with_word(source: Path, rendered: Path) -> None:
    """Render a DOCX read-only through Microsoft Word when LibreOffice is unavailable."""
    try:
        import win32com.client
    except ImportError as exc:
        raise ResumePaginationError(
            "DOCX pagination requires LibreOffice or Microsoft Word; provide a rendered PDF"
        ) from exc
    word = None
    document = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False)
        document.ExportAsFixedFormat(str(rendered), 17)
    except Exception as exc:
        raise ResumePaginationError(f"Microsoft Word DOCX render failed: {exc}") from exc
    finally:
        if document is not None:
            document.Close(False)
        if word is not None:
            word.Quit()


def _pdf_page_count(path: Path) -> int:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise ResumePaginationError(f"could not read rendered PDF page count: {path}") from exc


def inspect_resume_pages(path: str | Path) -> ResumePageReport:
    """Render if necessary and return the page count of the exact résumé artifact."""
    source = Path(path).resolve()
    if not source.is_file():
        raise ResumePaginationError(f"résumé artifact does not exist: {source}")
    suffix = source.suffix.casefold()
    if suffix == ".pdf":
        page_count = _pdf_page_count(source)
        return ResumePageReport(
            source_path=str(source),
            rendered_path=str(source),
            page_count=page_count,
            passed=page_count == REQUIRED_RESUME_PAGES,
        )
    if suffix != ".docx":
        raise ResumePaginationError("résumé page gate accepts only .pdf or .docx artifacts")

    with tempfile.TemporaryDirectory(prefix="resume-page-gate-") as temporary:
        output_dir = Path(temporary)
        profile = output_dir / "libreoffice-profile"
        profile.mkdir()
        rendered = output_dir / f"{source.stem}.pdf"
        soffice = _soffice_path()
        if soffice:
            command = [
                soffice,
                "--headless",
                f"-env:UserInstallation={profile.as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "unknown conversion error").strip()
                raise ResumePaginationError(f"LibreOffice DOCX render failed: {detail}")
        else:
            _render_docx_with_word(source, rendered)
        if not rendered.is_file() or rendered.stat().st_size == 0:
            raise ResumePaginationError("DOCX render did not produce a readable PDF")
        page_count = _pdf_page_count(rendered)
        return ResumePageReport(
            source_path=str(source),
            rendered_path="temporary LibreOffice PDF",
            page_count=page_count,
            passed=page_count == REQUIRED_RESUME_PAGES,
        )


def require_two_page_resume(path: str | Path) -> ResumePageReport:
    """Return a report or fail closed unless rendered output is exactly two pages."""
    report = inspect_resume_pages(path)
    if not report.passed:
        raise ResumePaginationError(
            f"résumé must render to exactly {report.required_pages} pages; got {report.page_count}"
        )
    return report


def visual_qa_receipt_path(
    resume_hash: str,
    root: str | Path = "data/resume_visual_qa",
    receipt_id: str | None = None,
) -> Path:
    if not receipt_id:
        raise ResumePaginationError("a versioned visual QA receipt ID is required")
    return Path(root) / resume_hash / "receipts" / f"{receipt_id}.json"


def render_visual_qa_previews(path: str | Path, output_dir: str | Path) -> list[Path]:
    """Deterministically render the exact two-page PDF for human inspection."""
    source = Path(path).resolve()
    require_two_page_resume(source)
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise ResumePaginationError("pdftoppm is required to create visual QA previews")
    if os.name == "nt" and Path(pdftoppm).suffix.casefold() in {".cmd", ".bat"}:
        native = Path(pdftoppm).resolve().parents[2] / "native/poppler/Library/bin/pdftoppm.exe"
        if native.is_file():
            pdftoppm = str(native)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    prefix = destination / "page"
    result = subprocess.run(
        [pdftoppm, "-png", "-r", "150", str(source), str(prefix)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    pages = sorted(destination.glob("page-*.png"))
    if result.returncode != 0 or len(pages) != REQUIRED_RESUME_PAGES:
        raise ResumePaginationError("failed to create exactly two visual QA previews")
    return pages


def record_visual_qa(
    path: str | Path,
    *,
    reviewer: str,
    confirmed: bool,
    root: str | Path = "data/resume_visual_qa",
    existing_preview_paths: list[str] | None = None,
) -> ResumeVisualQAReceipt:
    """Record explicit visual inspection of both pages, bound to exact PDF bytes."""
    source = Path(path).resolve()
    if source.suffix.casefold() != ".pdf":
        raise ResumePaginationError("visual QA must be recorded against the exact final PDF")
    report = require_two_page_resume(source)
    if not confirmed or not reviewer.strip():
        raise ResumePaginationError("explicit reviewer confirmation is required for visual QA")
    resume_hash = _sha256(source)
    with tempfile.TemporaryDirectory(prefix="resume-visual-proof-") as temporary:
        canonical = render_visual_qa_previews(source, temporary)
        canonical_hashes = [_sha256(item) for item in canonical]
        if existing_preview_paths is not None:
            inspected = [Path(item).resolve() for item in existing_preview_paths]
            if (
                len(inspected) != REQUIRED_RESUME_PAGES
                or len(set(inspected)) != REQUIRED_RESUME_PAGES
                or not all(item.is_file() for item in inspected)
                or [_sha256(item) for item in inspected] != canonical_hashes
            ):
                raise ResumePaginationError(
                    "inspected previews are not exact renders of this résumé PDF"
                )
        preview_dir = Path(root) / resume_hash / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        persisted: list[Path] = []
        for index, (generated, preview_hash) in enumerate(
            zip(canonical, canonical_hashes, strict=True), start=1
        ):
            destination = preview_dir / f"page-{index}-{preview_hash}.png"
            if destination.exists() and _sha256(destination) != preview_hash:
                raise ResumePaginationError("stored visual QA preview hash collision")
            if not destination.exists():
                shutil.copyfile(generated, destination)
            persisted.append(destination.resolve())
    preview_paths = [str(item) for item in persisted]
    preview_hashes = canonical_hashes
    payload = {
        "resume_hash": resume_hash,
        "page_count": report.page_count,
        "reviewer": reviewer.strip(),
        "reviewed_at": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="microseconds"),
        "preview_paths": preview_paths,
        "preview_hashes": preview_hashes,
    }
    receipt = ResumeVisualQAReceipt(
        receipt_id=_visual_receipt_id(payload),
        **payload,
    )
    receipt_path = visual_qa_receipt_path(resume_hash, root, receipt.receipt_id)
    if receipt_path.exists():
        existing = ResumeVisualQAReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        if existing != receipt:
            raise ResumePaginationError("visual QA receipt ID collision")
    else:
        _atomic_json(receipt_path, receipt.model_dump())
    return receipt


def require_visual_qa(
    path: str | Path,
    root: str | Path = "data/resume_visual_qa",
    *,
    receipt_path: str | Path | None = None,
) -> ResumeVisualQAReceipt:
    source = Path(path).resolve()
    resume_hash = _sha256(source)
    if receipt_path is None:
        candidates = list((Path(root) / resume_hash / "receipts").glob("*.json"))
        if not candidates:
            raise ResumePaginationError("visual QA receipt is required for the exact résumé PDF")
        receipts = [
            ResumeVisualQAReceipt.model_validate_json(item.read_text(encoding="utf-8"))
            for item in candidates
        ]
        receipt = max(receipts, key=lambda item: item.reviewed_at)
    else:
        receipt_file = Path(receipt_path)
        if not receipt_file.is_file():
            raise ResumePaginationError("visual QA receipt is required for the exact résumé PDF")
        receipt = ResumeVisualQAReceipt.model_validate_json(
            receipt_file.read_text(encoding="utf-8")
        )
    if receipt.resume_hash != resume_hash or receipt.page_count != REQUIRED_RESUME_PAGES:
        raise ResumePaginationError("visual QA receipt does not match the exact résumé PDF")
    payload = receipt.model_dump(exclude={"receipt_id"})
    if _visual_receipt_id(payload) != receipt.receipt_id:
        raise ResumePaginationError("visual QA receipt integrity check failed")
    previews = [Path(item).resolve() for item in receipt.preview_paths]
    if (
        len(previews) != REQUIRED_RESUME_PAGES
        or len(set(previews)) != REQUIRED_RESUME_PAGES
        or len(receipt.preview_hashes) != REQUIRED_RESUME_PAGES
        or not all(item.is_file() for item in previews)
    ):
        raise ResumePaginationError("visual QA requires exactly two existing page previews")
    if [_sha256(item) for item in previews] != receipt.preview_hashes:
        raise ResumePaginationError("visual QA preview bytes changed after review")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resume", help="PDF or DOCX résumé to validate")
    parser.add_argument("--record-visual-qa", action="store_true")
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()
    try:
        report = require_two_page_resume(args.resume)
    except ResumePaginationError as exc:
        raise SystemExit(f"BLOCKED: {exc}") from exc
    print(f"PASS: {report.source_path} renders to exactly {report.page_count} pages")
    if args.record_visual_qa:
        source = Path(args.resume).resolve()
        resume_hash = _sha256(source)
        preview_dir = Path("data/resume_visual_qa") / resume_hash / "inspection"
        try:
            previews = render_visual_qa_previews(source, preview_dir)
        except ResumePaginationError as exc:
            raise SystemExit(f"BLOCKED: {exc}") from exc
        for preview in previews:
            print(f"Inspect: {preview.resolve()}")
        confirmation = input(
            "Inspect both generated page previews. Type VERIFIED to confirm no visual defects: "
        )
        receipt = record_visual_qa(
            args.resume,
            reviewer=args.reviewer,
            confirmed=confirmation == "VERIFIED",
            existing_preview_paths=[str(item.resolve()) for item in previews],
        )
        print(f"VISUAL QA PASS: {receipt.receipt_id} by {receipt.reviewer}")


if __name__ == "__main__":
    main()
