"""Idempotent Google Drive archive for exact application résumé artifacts."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from apply.resume_artifact import FINAL_RESUME_MIME_TYPE, require_final_resume_pdf


_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
_NON_NAME = re.compile(r"[^A-Za-z0-9]+")


class ResumeArchiveRecord(BaseModel):
    package_id: str
    resume_hash: str
    resume_size: int
    drive_file_id: str
    drive_url: str
    drive_name: str
    folder_id: str
    archived_at: str


def archive_resume_name(
    company: str,
    suffix: str,
    *,
    applicant: str = "Evan Goh",
    date: datetime | None = None,
) -> str:
    """Return Evan_Goh_Company_Name_YYYY-MM-DD with the artifact extension."""
    when = date or datetime.now(ZoneInfo("Asia/Singapore"))

    def safe(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return _NON_NAME.sub("_", ascii_value).strip("_")

    extension = suffix.casefold() if suffix.startswith(".") else f".{suffix.casefold()}"
    if extension != ".pdf":
        raise ValueError("archived application résumé must be PDF-only")
    return f"{safe(applicant)}_{safe(company)}_{when.date().isoformat()}{extension}"


class GoogleDriveResumeArchive:
    """Upload and verify one exact résumé per immutable application package."""

    def __init__(
        self,
        service,
        folder_id: str,
        *,
        identity_email: str = "the configured service account",
        project_id: str = "",
        auth_mode: str = "oauth",
        intent_root: str | Path = "data/drive_upload_intents",
    ) -> None:
        if not folder_id.strip():
            raise ValueError("a dedicated Google Drive résumé folder ID is required")
        self.service = service
        self.folder_id = folder_id.strip()
        self.identity_email = identity_email
        self.project_id = project_id
        self.auth_mode = auth_mode
        self.intent_root = Path(intent_root)

    @classmethod
    def from_service_account_file(cls, path: str, folder_id: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            path, scopes=[_DRIVE_SCOPE]
        )
        return cls(
            build("drive", "v3", credentials=credentials, cache_discovery=False),
            folder_id,
            identity_email=credentials.service_account_email,
            project_id=credentials.project_id,
            auth_mode="service_account",
        )

    @classmethod
    def from_service_account_info(cls, info: dict, folder_id: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=[_DRIVE_SCOPE]
        )
        return cls(
            build("drive", "v3", credentials=credentials, cache_discovery=False),
            folder_id,
            identity_email=credentials.service_account_email,
            project_id=credentials.project_id,
            auth_mode="service_account",
        )

    @classmethod
    def from_user_refresh_token(
        cls,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        folder_id: str,
    ):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[_DRIVE_SCOPE],
        )
        return cls(
            build("drive", "v3", credentials=credentials, cache_discovery=False),
            folder_id,
            identity_email="configured Google user",
            auth_mode="oauth",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_folder_access(self) -> dict:
        """Fail clearly unless the configured folder accepts uploads by this identity."""
        try:
            folder = self.service.files().get(
                fileId=self.folder_id,
                fields="id,name,mimeType,driveId,capabilities(canAddChildren)",
                supportsAllDrives=True,
            ).execute()
        except Exception as exc:
            if "accessNotConfigured" in str(exc) or "API has not been used" in str(exc):
                console = (
                    "https://console.cloud.google.com/apis/library/drive.googleapis.com"
                    f"?project={self.project_id}"
                )
                raise RuntimeError(
                    f"Google Drive API is disabled for project {self.project_id}; enable it at {console}"
                ) from exc
            raise RuntimeError(
                "Google Drive résumé folder is not accessible; share it with "
                f"{self.identity_email} as Editor"
            ) from exc
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            raise RuntimeError("configured Drive résumé destination is not a folder")
        if not folder.get("capabilities", {}).get("canAddChildren", False):
            raise RuntimeError("configured Drive identity cannot add files to the résumé folder")
        if self.auth_mode == "service_account" and not folder.get("driveId"):
            raise RuntimeError(
                "service-account résumé uploads require a Shared Drive folder; use user OAuth "
                "for an ordinary My Drive folder"
            )
        return folder

    def _find_existing(self, package_id: str) -> dict | None:
        escaped = package_id.replace("'", "\\'")
        query = (
            f"'{self.folder_id}' in parents and trashed = false and "
            f"appProperties has {{ key='applicationPackageId' and value='{escaped}' }}"
        )
        response = self.service.files().list(
            q=query,
            spaces="drive",
            fields="files(id,name,webViewLink,size,md5Checksum,appProperties,parents)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = response.get("files", [])
        if len(files) > 1:
            raise RuntimeError("multiple Drive résumé files exist for one application package")
        return files[0] if files else None

    def _intent_path(self, package_id: str) -> Path:
        key = hashlib.sha256(package_id.encode("utf-8")).hexdigest()
        return self.intent_root / f"{key}.json"

    @contextmanager
    def _package_lock(self, package_id: str):
        """Serialize one package upload across local processes."""
        lock_path = self._intent_path(package_id).with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _load_or_create_intent(
        self, package_id: str, company: str, suffix: str, resume_hash: str
    ) -> dict:
        path = self._intent_path(package_id)
        if path.is_file():
            intent = json.loads(path.read_text(encoding="utf-8"))
            expected = {
                "package_id": package_id,
                "folder_id": self.folder_id,
                "resume_hash": resume_hash,
            }
            if any(intent.get(key) != value for key, value in expected.items()):
                raise RuntimeError("Drive upload intent does not match the immutable package")
            return intent
        archived_at = datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")
        name = archive_resume_name(
            company, suffix, applicant="Evan Goh", date=datetime.fromisoformat(archived_at)
        )
        generated = self.service.files().generateIds(count=1, space="drive", type="files").execute()
        ids = generated.get("ids", [])
        if len(ids) != 1:
            raise RuntimeError("Google Drive did not reserve an upload file ID")
        intent = {
            "package_id": package_id,
            "folder_id": self.folder_id,
            "resume_hash": resume_hash,
            "drive_file_id": ids[0],
            "drive_name": name,
            "archived_at": archived_at,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return intent

    def _get_file(self, file_id: str) -> dict:
        return self.service.files().get(
            fileId=file_id,
            fields="id,name,webViewLink,size,md5Checksum,appProperties,parents,trashed",
            supportsAllDrives=True,
        ).execute()

    def _remote_sha256(self, file_id: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload

        output = io.BytesIO()
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        downloader = MediaIoBaseDownload(output, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return hashlib.sha256(output.getvalue()).hexdigest()

    def validate_remote(
        self,
        record: ResumeArchiveRecord,
        *,
        expected_name: str | None = None,
    ) -> dict:
        try:
            remote = self.service.files().get(
                fileId=record.drive_file_id,
                fields="id,name,webViewLink,size,appProperties,parents,trashed",
                supportsAllDrives=True,
            ).execute()
        except Exception as exc:
            raise RuntimeError("archived résumé is no longer readable in Google Drive") from exc
        if remote.get("trashed"):
            raise RuntimeError("archived résumé is in Google Drive trash")
        if self.folder_id not in remote.get("parents", []):
            raise RuntimeError("archived résumé moved outside the configured Drive folder")
        if expected_name and remote.get("name") != expected_name:
            raise RuntimeError("archived résumé filename no longer matches the package")
        if remote.get("webViewLink") != record.drive_url:
            raise RuntimeError("archived résumé Drive link changed")
        if str(remote.get("size", "")) != str(record.resume_size):
            raise RuntimeError("archived résumé byte length changed")
        if remote.get("appProperties", {}).get("resumeSha256") != record.resume_hash:
            raise RuntimeError("archived résumé hash metadata changed")
        if remote.get("appProperties", {}).get("applicationPackageId") != record.package_id:
            raise RuntimeError("archived résumé package binding changed")
        if remote.get("appProperties", {}).get("archivedAtSgt") != record.archived_at:
            raise RuntimeError("archived résumé timestamp binding changed")
        if self._remote_sha256(record.drive_file_id) != record.resume_hash:
            raise RuntimeError("archived résumé bytes do not match the approved résumé")
        return remote

    def archive(
        self,
        *,
        package_id: str,
        company: str,
        resume_path: str | Path,
        expected_sha256: str,
        applicant: str = "Evan Goh",
    ) -> ResumeArchiveRecord:
        source = require_final_resume_pdf(resume_path)
        if applicant != "Evan Goh":
            raise ValueError("archive naming is fixed to Evan_Goh for this personal application system")
        self.verify_folder_access()
        with tempfile.TemporaryDirectory(prefix="resume-drive-stage-") as temporary:
            staged = Path(temporary) / source.name
            with source.open("rb") as incoming, staged.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            actual_hash = self._sha256(staged)
            if actual_hash != expected_sha256:
                raise ValueError("the résumé bytes do not match the immutable application package")
            require_final_resume_pdf(staged)
            with self._package_lock(package_id):
                existing = self._find_existing(package_id)
                if existing is not None:
                    archived_at = existing.get("appProperties", {}).get("archivedAtSgt", "")
                    if not archived_at:
                        raise RuntimeError("Drive archive is missing its immutable archive timestamp")
                    name = archive_resume_name(
                        company, source.suffix, applicant="Evan Goh",
                        date=datetime.fromisoformat(archived_at),
                    )
                else:
                    intent = self._load_or_create_intent(
                        package_id, company, source.suffix, actual_hash
                    )
                    name = intent["drive_name"]
                    archived_at = intent["archived_at"]
                    from googleapiclient.http import MediaFileUpload

                    media_type = FINAL_RESUME_MIME_TYPE
                    body = {
                        "id": intent["drive_file_id"],
                        "name": name,
                        "parents": [self.folder_id],
                        "appProperties": {
                            "applicationPackageId": package_id,
                            "resumeSha256": actual_hash,
                            "archivedAtSgt": archived_at,
                        },
                    }
                    try:
                        existing = self.service.files().create(
                            body=body,
                            media_body=MediaFileUpload(
                                str(staged), mimetype=media_type, resumable=False
                            ),
                            fields="id,name,webViewLink,size,md5Checksum,appProperties,parents",
                            supportsAllDrives=True,
                        ).execute()
                    except Exception:
                        try:
                            existing = self._get_file(intent["drive_file_id"])
                        except Exception:
                            raise
            staged_size = staged.stat().st_size
        properties = existing.get("appProperties", {})
        if properties.get("resumeSha256") != actual_hash:
            raise RuntimeError("Drive archive hash metadata does not match the packaged résumé")
        if properties.get("applicationPackageId") != package_id:
            raise RuntimeError("Drive archive package metadata does not match the package")
        if properties.get("archivedAtSgt") != archived_at:
            raise RuntimeError("Drive archive timestamp metadata does not match the upload intent")
        if str(existing.get("size", "")) != str(staged_size):
            raise RuntimeError("Drive archive byte length does not match the packaged résumé")
        if self.folder_id not in existing.get("parents", []):
            raise RuntimeError("Drive archive is not in the configured résumé folder")
        url = existing.get("webViewLink", "")
        if not url:
            raise RuntimeError("Drive did not return a verifiable file link")
        record = ResumeArchiveRecord(
            package_id=package_id,
            resume_hash=actual_hash,
            resume_size=staged_size,
            drive_file_id=existing["id"],
            drive_url=url,
            drive_name=existing["name"],
            folder_id=self.folder_id,
            archived_at=archived_at,
        )
        self.validate_remote(record, expected_name=name)
        return record


def load_drive_archive_config(path: str | Path = "data/google_drive_config.json") -> dict:
    config = Path(path)
    return json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
