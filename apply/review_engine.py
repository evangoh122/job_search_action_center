"""Immutable, review-first application packages and single-use approvals."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from apply.ats import ADAPTERS, ApplicationPlan
from apply.resume_models import ResumeAchievement
from apply.resume_artifact import FinalResumeArtifactError, require_final_resume_pdf
from apply.tailor import tailor
from config import MINIMUM_MONTHLY_SGD
from models import Applicant, ApplicationDraft, Job
from salary import SalaryRange, meets_monthly_sgd_floor
from resume_page_gate import (
    ResumePaginationError,
    inspect_resume_pages,
    require_two_page_resume,
    require_visual_qa,
    visual_qa_receipt_path,
)
from store.google_drive_resume_archive import ResumeArchiveRecord


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class ApplicationPackage(BaseModel):
    """Exact application payload reviewed and approved as one immutable unit."""

    schema_version: Literal[1] = 1
    package_id: str
    created_at: str
    job_id: str
    job_dedupe_key: str
    company: str
    title: str
    job_url: str
    job_description_hash: str
    provider: str
    form_url: str
    fields: dict[str, str] = Field(default_factory=dict)
    fields_hash: str
    cover_letter: str
    cover_letter_hash: str
    resume_path: str
    resume_hash: str
    resume_page_count: int
    resume_visual_qa_receipt_id: str
    resume_visual_qa_receipt_path: str
    resume_evidence_ids: list[str] = Field(default_factory=list)
    salary_review_cleared: bool = False

    def hash_payload(self) -> dict[str, object]:
        """Return the package content covered by its immutable identifier."""
        return self.model_dump(exclude={"package_id"})

    def expected_package_id(self) -> str:
        """Recompute the exact package identifier."""
        return _sha256_bytes(_canonical(self.hash_payload()))

    def intact(self) -> bool:
        """Return whether the stored package has not been modified."""
        return self.package_id == self.expected_package_id()


class ReviewFinding(BaseModel):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str


class ApplicationReview(BaseModel):
    package_id: str
    reviewed_at: str
    verdict: Literal["pass", "blocked"]
    findings: list[ReviewFinding] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


class ApprovalRecord(BaseModel):
    package_id: str
    package_hash: str
    vacancy_hash: str
    resume_hash: str
    fields_hash: str
    nonce: str
    approved_at: str
    expires_at: str
    consumed_at: str = ""
    revoked_at: str = ""


class ApplicationPackageStore:
    """Persist immutable packages and their automated reviews."""

    def __init__(self, root: str | Path = "data/application_packages") -> None:
        self.root = Path(root)

    def package_path(self, package_id: str) -> Path:
        return self.root / f"{package_id}.json"

    def review_path(self, package_id: str) -> Path:
        return self.root / f"{package_id}.review.json"

    def sync_path(self, package_id: str) -> Path:
        return self.root / f"{package_id}.sheets.json"

    def drive_path(self, package_id: str) -> Path:
        return self.root / f"{package_id}.drive.json"

    @staticmethod
    def _validate_artifact(package: ApplicationPackage) -> None:
        resume = require_final_resume_pdf(package.resume_path)
        if _sha256_bytes(resume.read_bytes()) != package.resume_hash:
            raise ValueError("application package résumé hash does not match its bytes")
        pagination = require_two_page_resume(resume)
        if pagination.page_count != package.resume_page_count:
            raise ValueError("application package résumé page count does not match")
        visual_qa = require_visual_qa(
            resume, receipt_path=package.resume_visual_qa_receipt_path
        )
        if visual_qa.receipt_id != package.resume_visual_qa_receipt_id:
            raise ValueError("application package visual-QA receipt does not match")

    def save_package(self, package: ApplicationPackage) -> Path:
        if not package.intact():
            raise ValueError("application package hash is invalid")
        self._validate_artifact(package)
        path = self.package_path(package.package_id)
        if path.exists():
            existing = ApplicationPackage.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != package:
                raise ValueError("package id collision or existing package was modified")
            return path
        _atomic_json(path, package.model_dump())
        return path

    def load_package(self, package_id: str) -> ApplicationPackage:
        package = ApplicationPackage.model_validate_json(
            self.package_path(package_id).read_text(encoding="utf-8")
        )
        if not package.intact():
            raise ValueError("application package failed integrity verification")
        self._validate_artifact(package)
        return package

    def save_review(self, review: ApplicationReview) -> Path:
        _atomic_json(self.review_path(review.package_id), review.model_dump())
        return self.review_path(review.package_id)

    def load_review(self, package_id: str) -> ApplicationReview:
        return ApplicationReview.model_validate_json(
            self.review_path(package_id).read_text(encoding="utf-8")
        )

    def record_sheets_sync(self, package_id: str, record_key: str) -> Path:
        package = self.load_package(package_id)
        value = {
            "package_id": package.package_id,
            "package_hash": package.expected_package_id(),
            "record_key": record_key,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_json(self.sync_path(package_id), value)
        return self.sync_path(package_id)

    def record_drive_archive(self, record: ResumeArchiveRecord) -> Path:
        package = self.load_package(record.package_id)
        if record.resume_hash != package.resume_hash:
            raise ValueError("Drive archive does not match the packaged résumé hash")
        _atomic_json(self.drive_path(package.package_id), record.model_dump())
        return self.drive_path(package.package_id)

    def load_drive_archive(self, package_id: str) -> ResumeArchiveRecord:
        return ResumeArchiveRecord.model_validate_json(
            self.drive_path(package_id).read_text(encoding="utf-8")
        )

    def drive_archive_is_current(self, package: ApplicationPackage) -> bool:
        path = self.drive_path(package.package_id)
        if not path.is_file():
            return False
        record = ResumeArchiveRecord.model_validate_json(path.read_text(encoding="utf-8"))
        return (
            record.package_id == package.package_id
            and record.resume_hash == package.resume_hash
            and bool(record.drive_file_id)
            and bool(record.drive_url)
        )

    def sheets_sync_is_current(self, package: ApplicationPackage) -> bool:
        path = self.sync_path(package.package_id)
        if not path.is_file():
            return False
        value = json.loads(path.read_text(encoding="utf-8"))
        return (
            value.get("package_id") == package.package_id
            and value.get("package_hash") == package.expected_package_id()
            and bool(value.get("record_key"))
        )


class ApprovalStore:
    """Maintain expiring, exact-package, single-use human approvals."""

    def __init__(self, path: str | Path = "data/application_approvals_v2.json") -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, ApprovalRecord]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: ApprovalRecord.model_validate(value) for key, value in raw.items()}

    def _save(self, records: dict[str, ApprovalRecord]) -> None:
        _atomic_json(self.path, {key: value.model_dump() for key, value in records.items()})

    def get(self, package_id: str) -> ApprovalRecord | None:
        with self._locked():
            return self._load().get(package_id)

    def approve(self, package: ApplicationPackage, review: ApplicationReview, ttl_minutes: int = 30) -> ApprovalRecord:
        if not package.intact() or review.package_id != package.package_id or not review.passed:
            raise ValueError("only an intact package with a passing review can be approved")
        now = datetime.now(timezone.utc)
        record = ApprovalRecord(
            package_id=package.package_id,
            package_hash=package.expected_package_id(),
            vacancy_hash=package.job_description_hash,
            resume_hash=package.resume_hash,
            fields_hash=package.fields_hash,
            nonce=secrets.token_urlsafe(24),
            approved_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        )
        with self._locked():
            records = self._load()
            records[package.package_id] = record
            self._save(records)
        return record

    def consume(self, package: ApplicationPackage) -> ApprovalRecord:
        with self._locked():
            records = self._load()
            record = records.get(package.package_id)
            if record is None:
                raise ValueError("exact-package approval is required")
            if record.consumed_at:
                raise ValueError("approval has already been consumed")
            if record.revoked_at:
                raise ValueError("approval has been revoked")
            if record.package_hash != package.expected_package_id() or not package.intact():
                raise ValueError("approval does not match the current package")
            if datetime.now(timezone.utc) >= datetime.fromisoformat(record.expires_at):
                raise ValueError("approval has expired")
            record.consumed_at = datetime.now(timezone.utc).isoformat()
            records[package.package_id] = record
            self._save(records)
        return record

    def revoke(self, package_id: str) -> ApprovalRecord:
        with self._locked():
            records = self._load()
            record = records.get(package_id)
            if record is None:
                raise ValueError("no approval exists for this package")
            if not record.consumed_at:
                record.revoked_at = datetime.now(timezone.utc).isoformat()
                records[package_id] = record
                self._save(records)
        return record


def review_package(package: ApplicationPackage) -> ApplicationReview:
    """Run deterministic pre-application safety and completeness checks."""
    findings: list[ReviewFinding] = []

    def add(code: str, severity: Literal["blocker", "warning", "info"], message: str) -> None:
        findings.append(ReviewFinding(code=code, severity=severity, message=message))

    if not package.intact():
        add("package_tampered", "blocker", "Package content no longer matches its identifier.")
    if _sha256_bytes(_canonical(package.fields)) != package.fields_hash:
        add("fields_tampered", "blocker", "Application answers changed after packaging.")
    if _sha256_bytes(package.cover_letter.encode("utf-8")) != package.cover_letter_hash:
        add("cover_letter_tampered", "blocker", "Cover letter changed after packaging.")
    resume = Path(package.resume_path)
    if not resume.is_file():
        add("resume_missing", "blocker", "The reviewed resume artifact is missing.")
    elif _sha256_bytes(resume.read_bytes()) != package.resume_hash:
        add("resume_tampered", "blocker", "The resume bytes changed after packaging.")
    else:
        try:
            require_final_resume_pdf(resume)
        except FinalResumeArtifactError as exc:
            add("resume_not_pdf", "blocker", str(exc))
        else:
            try:
                pagination = inspect_resume_pages(resume)
                if pagination.page_count != package.resume_page_count:
                    add("resume_pagination_changed", "blocker", "Rendered résumé page count changed.")
                if not pagination.passed:
                    add(
                        "resume_not_two_pages",
                        "blocker",
                        f"Résumé must render to exactly two pages; got {pagination.page_count}.",
                    )
                visual_qa = require_visual_qa(
                    resume, receipt_path=package.resume_visual_qa_receipt_path
                )
                if visual_qa.receipt_id != package.resume_visual_qa_receipt_id:
                    add("resume_visual_qa_changed", "blocker", "Visual QA receipt changed.")
            except ResumePaginationError as exc:
                add("resume_pagination_unverified", "blocker", str(exc))
    parsed = urlparse(package.form_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        add("invalid_form_url", "blocker", "The employer form URL is invalid.")
    for field in ("name", "email", "phone"):
        if not package.fields.get(field):
            add(f"missing_{field}", "blocker", f"Required applicant field is missing: {field}.")
    if any("password" in key.casefold() for key in package.fields):
        add("password_in_package", "blocker", "Passwords must never be stored in an application package.")
    if not package.cover_letter.strip():
        add("cover_letter_missing", "blocker", "Cover letter is empty.")
    if not package.salary_review_cleared:
        add("salary_review", "blocker", "Salary floor is unresolved; record a vacancy-specific override after review.")
    if not package.resume_evidence_ids:
        add("whole_resume", "info", "Using the verified whole master-resume artifact; no rewritten evidence blocks.")
    add("manual_confirmation", "info", "Final employer submission still requires the exact-package approval gate.")
    return ApplicationReview(
        package_id=package.package_id,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        verdict="blocked" if any(item.severity == "blocker" for item in findings) else "pass",
        findings=findings,
    )


class ReviewFirstApplicationEngine:
    """Prepare, review, approve, and execute one exact application package."""

    def __init__(
        self,
        applicant: Applicant,
        *,
        package_store: ApplicationPackageStore | None = None,
        approval_store: ApprovalStore | None = None,
        base_summary: str = "",
        achievements: list[ResumeAchievement] | None = None,
        visual_qa_root: str | Path = "data/resume_visual_qa",
        authority_validator: Callable[
            [ApplicationPackage, ResumeArchiveRecord, set[str]], None
        ] | None = None,
    ) -> None:
        self.applicant = applicant
        self.package_store = package_store or ApplicationPackageStore()
        self.approval_store = approval_store or ApprovalStore()
        self.base_summary = base_summary
        self.achievements = achievements or []
        self.visual_qa_root = Path(visual_qa_root)
        self.authority_validator = authority_validator

    def _validate_authority(
        self, package: ApplicationPackage, allowed_statuses: set[str]
    ) -> ResumeArchiveRecord:
        if self.authority_validator is None:
            raise ValueError("live Google Drive and Sheets validation is required")
        archive = self.package_store.load_drive_archive(package.package_id)
        self.authority_validator(package, archive, allowed_statuses)
        return archive

    def prepare(
        self,
        job: Job,
        *,
        resume_path: str,
        salary_override: bool = False,
    ) -> tuple[ApplicationPackage, ApplicationReview, ApplicationDraft, ApplicationPlan]:
        builder = ADAPTERS.get((job.ats_type or "").casefold())
        if builder is None:
            raise ValueError(f"unsupported hosted application provider: {job.ats_type or 'unknown'}")
        resume = require_final_resume_pdf(resume_path)
        pagination = require_two_page_resume(resume)
        visual_qa = require_visual_qa(resume, self.visual_qa_root)
        applicant = self.applicant.model_copy(update={"resume_path": str(resume)})
        plan = builder(job, applicant)
        draft = tailor(job, self.base_summary, applicant.name, achievements=self.achievements)
        fields = {**plan.fields, "cover_letter": draft.cover_letter}
        salary = SalaryRange(job.salary_min, job.salary_max, job.salary_currency, job.salary_period)
        salary_cleared = meets_monthly_sgd_floor(salary, MINIMUM_MONTHLY_SGD) or salary_override
        created_at = datetime.now(timezone.utc).isoformat()
        content = {
            "schema_version": 1,
            "created_at": created_at,
            "job_id": job.id,
            "job_dedupe_key": job.dedupe_key,
            "company": job.company_canonical,
            "title": job.title,
            "job_url": job.url,
            "job_description_hash": _sha256_bytes(job.description.encode("utf-8")),
            "provider": plan.provider,
            "form_url": plan.form_url,
            "fields": fields,
            "fields_hash": _sha256_bytes(_canonical(fields)),
            "cover_letter": draft.cover_letter,
            "cover_letter_hash": _sha256_bytes(draft.cover_letter.encode("utf-8")),
            "resume_path": str(resume),
            "resume_hash": _sha256_bytes(resume.read_bytes()),
            "resume_page_count": pagination.page_count,
            "resume_visual_qa_receipt_id": visual_qa.receipt_id,
            "resume_visual_qa_receipt_path": str(
                visual_qa_receipt_path(
                    visual_qa.resume_hash, self.visual_qa_root, visual_qa.receipt_id
                ).resolve()
            ),
            "resume_evidence_ids": draft.resume_evidence_ids,
            "salary_review_cleared": salary_cleared,
        }
        package = ApplicationPackage(package_id=_sha256_bytes(_canonical(content)), **content)
        self.package_store.save_package(package)
        review = review_package(package)
        self.package_store.save_review(review)
        return package, review, draft, ApplicationPlan(
            provider=plan.provider,
            form_url=plan.form_url,
            fields=fields,
            resume_path=str(resume),
            resume_sha256=content["resume_hash"],
        )

    def approve(self, package_id: str, ttl_minutes: int = 30) -> ApprovalRecord:
        package = self.package_store.load_package(package_id)
        if not self.package_store.drive_archive_is_current(package):
            raise ValueError("exact résumé must be archived in Google Drive before approval")
        if not self.package_store.sheets_sync_is_current(package):
            raise ValueError("exact package must be synced to Google Sheets before approval")
        self._validate_authority(package, {"review_passed", "approved"})
        review = review_package(package)
        self.package_store.save_review(review)
        return self.approval_store.approve(package, review, ttl_minutes=ttl_minutes)

    def revoke(self, package_id: str) -> ApprovalRecord:
        return self.approval_store.revoke(package_id)

    def open_for_review(self, package_id: str, job: Job, filler) -> str:
        """Consume one approval and autofill, but never submit, a visible form."""
        package = self.package_store.load_package(package_id)
        if not self.package_store.drive_archive_is_current(package):
            return "drive_archive_required"
        if not self.package_store.sheets_sync_is_current(package):
            return "sheets_sync_required"
        try:
            self._validate_authority(package, {"approved"})
        except (OSError, ValueError, RuntimeError):
            return "authority_validation_failed"
        review = review_package(package)
        if not review.passed:
            self.package_store.save_review(review)
            return "review_blocked"
        current_description_hash = _sha256_bytes(job.description.encode("utf-8"))
        if (
            job.id != package.job_id
            or job.dedupe_key != package.job_dedupe_key
            or job.url != package.job_url
            or current_description_hash != package.job_description_hash
        ):
            return "vacancy_changed"
        self.approval_store.consume(package)
        plan = ApplicationPlan(
            provider=package.provider,
            form_url=package.form_url,
            fields=package.fields,
            resume_path=package.resume_path,
            resume_sha256=package.resume_hash,
        )
        return filler(job, self.applicant.model_copy(update={"resume_path": package.resume_path}), plan)
