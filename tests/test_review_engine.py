from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest
from PyPDF2 import PdfWriter

from apply import browser_submitter
from apply.review_engine import (
    ApplicationPackageStore,
    ApprovalStore,
    ReviewFirstApplicationEngine,
    review_package,
)
from models import Applicant, Job
from store.google_drive_resume_archive import ResumeArchiveRecord
from resume_page_gate import record_visual_qa


def _job() -> Job:
    return Job(
        id="job-1",
        source="test",
        company_canonical="Acme",
        dedupe_key="acme|data-scientist|123",
        title="Data Scientist",
        url="https://jobs.lever.co/acme/123",
        ats_type="lever",
        description="Build governed machine-learning systems.",
        salary_min=12_000,
        salary_max=14_000,
        salary_currency="SGD",
        salary_period="MONTH",
    )


@pytest.fixture
def engine(tmp_path):
    if shutil.which("pdftoppm") is None:
        pytest.skip("poppler-utils (pdftoppm) not installed; required for visual QA previews")
    resume = tmp_path / "resume.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with resume.open("wb") as output:
        writer.write(output)
    visual_root = tmp_path / "visual-qa"
    record_visual_qa(
        resume,
        reviewer="test reviewer",
        confirmed=True,
        root=visual_root,
    )
    instance = ReviewFirstApplicationEngine(
        Applicant(name="Alice Smith", email="alice@example.com", phone="+6512345678"),
        package_store=ApplicationPackageStore(tmp_path / "packages"),
        approval_store=ApprovalStore(tmp_path / "approvals.json"),
        base_summary="Data science leader",
        visual_qa_root=visual_root,
        authority_validator=lambda package, archive, statuses: None,
    )
    return instance, resume


def _prepare_and_sync(engine, resume):
    package, review, draft, plan = engine.prepare(_job(), resume_path=str(resume))
    _record_drive(engine, package)
    engine.package_store.record_sheets_sync(package.package_id, package.package_id)
    return package, review, draft, plan


def _record_drive(engine, package):
    engine.package_store.record_drive_archive(ResumeArchiveRecord(
        package_id=package.package_id,
        resume_hash=package.resume_hash,
        resume_size=Path(package.resume_path).stat().st_size,
        drive_file_id="drive-file-1",
        drive_url="https://drive.google.com/file/d/drive-file-1/view",
        drive_name="Evan_Goh_Acme_2026-07-19.pdf",
        folder_id="folder-1",
        archived_at="2026-07-19T12:00:00+08:00",
    ))


def test_prepare_hashes_exact_resume_answers_and_vacancy(engine):
    instance, resume = engine
    package, review, _, _ = _prepare_and_sync(instance, resume)
    assert package.intact()
    assert review.passed
    assert len(package.resume_hash) == 64
    assert len(package.fields_hash) == 64
    assert len(package.job_description_hash) == 64
    assert package.resume_page_count == 2


def test_prepare_rejects_docx_even_if_file_exists(engine, tmp_path):
    instance, _ = engine
    source = tmp_path / "resume.docx"
    source.write_bytes(b"PK fake docx")
    with pytest.raises(ValueError, match="must be a .pdf"):
        instance.prepare(_job(), resume_path=str(source))


def test_package_store_rejects_self_consistent_non_pdf_package(engine, tmp_path):
    import hashlib
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    source = tmp_path / "resume.docx"
    source.write_bytes(b"PK fake docx")
    bad = package.model_copy(update={
        "resume_path": str(source),
        "resume_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
    })
    bad = bad.model_copy(update={"package_id": bad.expected_package_id()})
    with pytest.raises(ValueError, match="must be a .pdf"):
        instance.package_store.save_package(bad)


def test_resume_change_blocks_review_and_approval(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    resume.write_bytes(b"changed after review")
    review = review_package(package)
    assert not review.passed
    assert "resume_tampered" in {finding.code for finding in review.findings}
    with pytest.raises(ValueError, match="PDF bytes|hash"):
        instance.approve(package.package_id)


def test_package_file_tampering_is_detected_on_load(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    path = instance.package_store.package_path(package.package_id)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["title"] = "Different role"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        instance.package_store.load_package(package.package_id)


def test_approval_requires_durable_sheets_sync(engine):
    instance, resume = engine
    package, review, _, _ = instance.prepare(_job(), resume_path=str(resume))
    assert review.passed
    _record_drive(instance, package)
    with pytest.raises(ValueError, match="Google Sheets"):
        instance.approve(package.package_id)


def test_approval_requires_exact_resume_drive_archive(engine):
    instance, resume = engine
    package, review, _, _ = instance.prepare(_job(), resume_path=str(resume))
    assert review.passed
    instance.package_store.record_sheets_sync(package.package_id, package.package_id)
    with pytest.raises(ValueError, match="Google Drive"):
        instance.approve(package.package_id)


def test_approval_is_exact_expiring_and_single_use(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    instance.approve(package.package_id)
    calls = []
    result = instance.open_for_review(
        package.package_id,
        _job(),
        lambda job, applicant, plan: calls.append(plan) or "ready_for_manual_submit",
    )
    assert result == "ready_for_manual_submit"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="already been consumed"):
        instance.open_for_review(package.package_id, _job(), lambda *_: "unexpected")

    second, _, _, _ = instance.prepare(_job().model_copy(update={"id": "job-2"}), resume_path=str(resume))
    _record_drive(instance, second)
    instance.package_store.record_sheets_sync(second.package_id, second.package_id)
    instance.approve(second.package_id, ttl_minutes=0)
    with pytest.raises(ValueError, match="expired"):
        instance.open_for_review(
            second.package_id,
            _job().model_copy(update={"id": "job-2"}),
            lambda *_: "unexpected",
        )


def test_changed_vacancy_does_not_launch_or_consume(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    instance.approve(package.package_id)
    changed = _job().model_copy(update={"description": "Vacancy text changed."})
    assert instance.open_for_review(package.package_id, changed, lambda *_: "unexpected") == "vacancy_changed"
    assert not instance.approval_store.get(package.package_id).consumed_at


def test_revoked_approval_cannot_open(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    instance.approve(package.package_id)
    instance.revoke(package.package_id)
    with pytest.raises(ValueError, match="revoked"):
        instance.open_for_review(package.package_id, _job(), lambda *_: "unexpected")


def test_remote_authority_failure_blocks_approval_and_open(engine):
    instance, resume = engine
    package, _, _, _ = _prepare_and_sync(instance, resume)
    instance.authority_validator = lambda *_: (_ for _ in ()).throw(
        RuntimeError("remote authority unavailable")
    )
    with pytest.raises(RuntimeError, match="remote authority unavailable"):
        instance.approve(package.package_id)

    instance.authority_validator = lambda *_: None
    instance.approve(package.package_id)
    instance.authority_validator = lambda *_: (_ for _ in ()).throw(
        RuntimeError("remote authority changed")
    )
    assert instance.open_for_review(
        package.package_id, _job(), lambda *_: "unexpected"
    ) == "authority_validation_failed"
    assert not instance.approval_store.get(package.package_id).consumed_at


def test_browser_filler_contains_no_submit_click_path():
    source = inspect.getsource(browser_submitter.PlaywrightApplicationFiller.__call__)
    assert ".click(" not in source
    assert "button[type='submit']" not in source
