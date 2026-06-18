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
    score: float | None = None
    tier: str | None = None
    status: str = "new"
    notes: str = ""


class Contact(BaseModel):
    id: str
    name: str
    company_canonical: str
    role: str = ""
    linkedin_url: str = ""
    email: str = ""
    notes: str = ""
