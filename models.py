from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RawJob(BaseModel):
    source: str
    company: str
    title: str
    url: str
    posted_at: datetime | None = None
    ats_type: str | None = None
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""


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
    # Retain every observed board link while keeping source/url compatible.
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, str] = Field(default_factory=dict)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_average: float | None = None
    salary_currency: str = ""
    salary_period: str = ""


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
    resume_path: str = ""
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    location: str = "Singapore"
    current_company: str = ""
    work_authorization: str = ""
    sponsorship_required: str = ""
    notice_period: str = ""
    salary_expectation: str = ""
    answers: dict[str, str] = Field(default_factory=dict)


class ApplicationDraft(BaseModel):
    job_id: str
    company: str
    title: str
    url: str
    cover_letter: str
    application_link: str = ""
    resume_filename: str = ""
    resume_version_id: str = ""
    resume_evidence_ids: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    resume_keywords: list[str] = Field(default_factory=list)
    resume_bullets: list[str] = Field(default_factory=list)
    resume_text: str = ""
    resume_fit_brief: dict[str, object] = Field(default_factory=dict)
    resume_keyword_map: list[dict[str, object]] = Field(default_factory=list)
    resume_selected_evidence: list[dict[str, object]] = Field(default_factory=list)
    resume_evidence_gaps: list[str] = Field(default_factory=list)
    resume_change_log: list[str] = Field(default_factory=list)
    resume_pagination_status: str = ""
    status: str = "drafted"  # drafted -> approved -> applied


class LinkedInPostMatch(BaseModel):
    id: str
    job_id: str
    job_key: str
    company: str
    job_title: str
    job_url: str
    post_url: str
    post_text: str
    posted_at: datetime | None = None
    author_name: str = ""
    author_title: str = ""
    author_profile_url: str = ""
    author_role_type: str = ""
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    post_intent: str = "hiring"
    status: str = "review_required"
