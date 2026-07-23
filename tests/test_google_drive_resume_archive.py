from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from PyPDF2 import PdfWriter

from store.google_drive_resume_archive import GoogleDriveResumeArchive, archive_resume_name


def _pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)
    return path


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value() if callable(self.value) else self.value


class _FakeFiles:
    def __init__(self, source):
        self.source = source
        self.created = []
        self.remote = None
        self.raise_after_create = False

    def generateIds(self, **kwargs):
        return _Request({"ids": ["file-1"]})

    def get(self, *, fileId, **kwargs):
        if fileId == "folder-1":
            return _Request({
                "id": "folder-1",
                "name": "Job Application Resumes",
                "mimeType": "application/vnd.google-apps.folder",
                "capabilities": {"canAddChildren": True},
            })
        return _Request(self.remote)

    def list(self, **kwargs):
        return _Request({"files": [self.remote] if self.remote else []})

    def create(self, *, body, media_body, **kwargs):
        def create_value():
            self.created.append(body)
            self.remote = {
                "id": body["id"],
                "name": body["name"],
                "webViewLink": "https://drive.google.com/file/d/file-1/view",
                "size": str(self.source.stat().st_size),
                "appProperties": body["appProperties"],
                "parents": body["parents"],
                "trashed": False,
            }
            if self.raise_after_create:
                raise ConnectionError("response lost after successful create")
            return self.remote
        return _Request(create_value)


class _FakeService:
    def __init__(self, source):
        self.files_api = _FakeFiles(source)

    def files(self):
        return self.files_api


def test_archive_name_uses_applicant_company_and_singapore_date():
    when = datetime(2026, 7, 20, 0, 5, tzinfo=ZoneInfo("Asia/Singapore"))
    assert archive_resume_name("United Overseas Bank (UOB)", ".pdf", date=when) == (
        "Evan_Goh_United_Overseas_Bank_UOB_2026-07-20.pdf"
    )


def test_archive_name_rejects_docx_even_when_name_is_otherwise_valid():
    when = datetime(2026, 7, 19, 23, 59, tzinfo=ZoneInfo("Asia/Singapore"))
    with pytest.raises(ValueError, match="PDF-only"):
        archive_resume_name("Mizuho / APAC", "DOCX", date=when)


def test_archive_name_rejects_non_resume_formats():
    with pytest.raises(ValueError, match="PDF-only"):
        archive_resume_name("UOB", ".txt")


def test_archive_rejects_fake_pdf_header_before_drive_write(tmp_path):
    source = tmp_path / "resume.pdf"
    source.write_bytes(b"%PDF-not-a-real-document")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    with pytest.raises(ValueError, match="structurally readable PDF"):
        archive.archive(
            package_id="package-1", company="UOB", resume_path=source,
            expected_sha256=digest,
        )
    assert service.files_api.created == []


def test_archive_create_and_retry_are_idempotent_and_byte_verified(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    first = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    second = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    assert first.drive_file_id == second.drive_file_id == "file-1"
    assert first.resume_size == source.stat().st_size
    assert len(service.files_api.created) == 1


def test_archive_recovers_lost_create_response_by_reserved_file_id(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    service.files_api.raise_after_create = True
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    record = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    assert record.drive_file_id == "file-1"
    assert len(service.files_api.created) == 1
    assert list((tmp_path / "intents").glob("*.json"))


def test_remote_rename_or_byte_change_fails_validation(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    record = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    service.files_api.remote["name"] = "renamed.pdf"
    with pytest.raises(RuntimeError, match="filename"):
        archive.validate_remote(record, expected_name="Evan_Goh_UOB_2026-07-19.pdf")
    service.files_api.remote["name"] = record.drive_name
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: "0" * 64)
    with pytest.raises(RuntimeError, match="bytes"):
        archive.validate_remote(record, expected_name=record.drive_name)


def test_retry_uses_original_singapore_archive_date(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    service.files_api.remote["appProperties"]["archivedAtSgt"] = "2026-07-18T23:59:59+08:00"
    service.files_api.remote["name"] = "Evan_Goh_UOB_2026-07-18.pdf"
    retry = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    assert retry.archived_at == "2026-07-18T23:59:59+08:00"
    assert retry.drive_name == "Evan_Goh_UOB_2026-07-18.pdf"


def test_remote_package_binding_change_fails(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    record = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    service.files_api.remote["appProperties"]["applicationPackageId"] = "other-package"
    with pytest.raises(RuntimeError, match="package binding"):
        archive.validate_remote(record, expected_name=record.drive_name)


def test_remote_archive_timestamp_change_fails(tmp_path, monkeypatch):
    source = _pdf(tmp_path / "resume.pdf")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    service = _FakeService(source)
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="oauth", intent_root=tmp_path / "intents"
    )
    monkeypatch.setattr(archive, "_remote_sha256", lambda file_id: digest)
    record = archive.archive(
        package_id="package-1", company="UOB", resume_path=source,
        expected_sha256=digest,
    )
    service.files_api.remote["appProperties"]["archivedAtSgt"] = "2026-07-20T00:00:00+08:00"
    with pytest.raises(RuntimeError, match="timestamp binding"):
        archive.validate_remote(record, expected_name=record.drive_name)


def test_service_account_rejects_ordinary_my_drive_folder(tmp_path):
    service = _FakeService(tmp_path / "unused")
    archive = GoogleDriveResumeArchive(
        service, "folder-1", auth_mode="service_account", project_id="project-1"
    )
    with pytest.raises(RuntimeError, match="Shared Drive"):
        archive.verify_folder_access()
