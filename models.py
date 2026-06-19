from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RawJob(BaseModel):
    source: str
    company: str
    title: str
    url: str
    posted_at: datetime | None = None
    ats_type: str | None = None
    description: str = ""


class Job(BaseModel):
    id: str
    source: str
    company_canonical: str
    dedupe_key: str
    title: str
    url: str
    ats_type: str | None = None
    posted_at: datetime | None = None
    description: str = ""
    score: float | None = None
    tier: str | None = None
    status: str = "new"
    notes: str = ""


class Contact(BaseModel):
    id: str
    name: str
    company_canonical: str
    role: str = ""
    role_type: str = ""  # "recruiter" | "hiring_manager" | ""
    linkedin_url: str = ""
    email: str = ""
    confidence: int = 0  # Hunter email confidence 0-100
    notes: str = ""


class EmailDraft(BaseModel):
    job_id: str
    company: str
    to_email: str
    to_name: str
    role_type: str  # "recruiter" | "hiring_manager"
    subject: str
    body: str


class Applicant(BaseModel):
    name: str
    email: str
    resume_url: str = ""
    phone: str = ""
    linkedin_url: str = ""


class ApplicationDraft(BaseModel):
    job_id: str
    company: str
    title: str
    url: str
    cover_letter: str
    matched_keywords: list[str] = []
    status: str = "drafted"  # drafted -> approved -> applied
