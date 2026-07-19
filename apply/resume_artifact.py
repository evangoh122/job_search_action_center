"""Single fail-closed contract for final résumé artifacts used in applications."""
from __future__ import annotations

import hashlib
import hmac
import tempfile
from contextlib import contextmanager
from pathlib import Path

from PyPDF2 import PdfReader


FINAL_RESUME_EXTENSION = ".pdf"
FINAL_RESUME_MIME_TYPE = "application/pdf"


class FinalResumeArtifactError(ValueError):
    """Raised when an application tries to use anything except a real PDF file."""


def require_final_resume_pdf(path: str | Path) -> Path:
    """Return the resolved artifact only when it is an existing PDF by name and bytes."""
    artifact = Path(path).resolve()
    if artifact.suffix.casefold() != FINAL_RESUME_EXTENSION:
        raise FinalResumeArtifactError(
            "final application résumé must be a .pdf file; DOCX is editing-source only"
        )
    if not artifact.is_file():
        raise FinalResumeArtifactError(f"final application résumé does not exist: {artifact}")
    with artifact.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise FinalResumeArtifactError(
                "final application résumé has a .pdf name but does not contain PDF bytes"
            )
    try:
        reader = PdfReader(str(artifact), strict=True)
        if reader.is_encrypted:
            raise FinalResumeArtifactError("final application résumé PDF must not be encrypted")
        if len(reader.pages) < 1:
            raise FinalResumeArtifactError("final application résumé PDF contains no pages")
        for page in reader.pages:
            _ = page.mediabox
    except FinalResumeArtifactError:
        raise
    except Exception as exc:
        raise FinalResumeArtifactError(
            "final application résumé is not a structurally readable PDF"
        ) from exc
    return artifact


def require_final_resume_filename(filename: str) -> str:
    """Reject non-PDF filenames before they enter Sheets or package metadata."""
    if Path(filename).suffix.casefold() != FINAL_RESUME_EXTENSION:
        raise FinalResumeArtifactError("application résumé filename must end in .pdf")
    return filename


@contextmanager
def stage_approved_resume_pdf(path: str | Path, expected_sha256: str):
    """Stage, hash, parse, and yield the immutable bytes used by a browser upload."""
    if len(expected_sha256) != 64:
        raise FinalResumeArtifactError("approved résumé SHA-256 is required before upload")
    source = require_final_resume_pdf(path)
    with tempfile.TemporaryDirectory(prefix="approved-resume-upload-") as temporary:
        staged = Path(temporary) / source.name
        digest = hashlib.sha256()
        with source.open("rb") as incoming, staged.open("wb") as outgoing:
            while chunk := incoming.read(1024 * 1024):
                outgoing.write(chunk)
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), expected_sha256.casefold()):
            raise FinalResumeArtifactError(
                "résumé bytes changed after approval; browser upload is blocked"
            )
        require_final_resume_pdf(staged)
        yield staged
