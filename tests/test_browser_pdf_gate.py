from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace

import pytest
from PyPDF2 import PdfWriter

from apply.ats import ApplicationPlan
from apply.browser_submitter import PlaywrightApplicationFiller
from apply.resume_artifact import FinalResumeArtifactError
from models import Applicant, Job


def _pdf(path, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)
    return path


class _Upload:
    def __init__(self):
        self.uploaded = []
        self.first = self

    def count(self):
        return 1

    def set_input_files(self, path):
        self.uploaded.append(path)


class _Page:
    def __init__(self, upload):
        self.upload = upload

    def goto(self, *args, **kwargs):
        return None

    def locator(self, selector):
        assert selector == "input[type='file']"
        return self.upload


class _Context:
    def __init__(self, page):
        self.pages = [page]

    def close(self):
        return None


class _PlaywrightManager:
    def __init__(self, page):
        self.value = SimpleNamespace(
            chromium=SimpleNamespace(
                launch_persistent_context=lambda *args, **kwargs: _Context(page)
            )
        )

    def __enter__(self):
        return self.value

    def __exit__(self, *args):
        return False


def test_browser_never_uploads_pdf_bytes_changed_after_approval(tmp_path, monkeypatch):
    resume = _pdf(tmp_path / "resume.pdf")
    approved_hash = hashlib.sha256(resume.read_bytes()).hexdigest()
    resume.write_bytes(resume.read_bytes() + b"changed-after-approval")
    upload = _Upload()
    page = _Page(upload)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: _PlaywrightManager(page)),
    )
    job = Job(
        id="j1", source="test", company_canonical="Acme", dedupe_key="acme|role",
        title="Data Scientist", url="https://example.com/job", description="role",
    )
    plan = ApplicationPlan(
        provider="test", form_url=job.url, fields={}, resume_path=str(resume),
        resume_sha256=approved_hash,
    )
    filler = PlaywrightApplicationFiller(wait_for_user=False)
    with pytest.raises(FinalResumeArtifactError, match="changed after approval"):
        filler(job, Applicant(name="Evan Goh", email="evan@example.com"), plan)
    assert upload.uploaded == []
