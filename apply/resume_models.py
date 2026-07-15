from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeAchievement(BaseModel):
    """Structured proof for one resume bullet.

    Keep the metric/result honest: the generator should rephrase this evidence, not invent it.
    """

    keyword: str
    result: str
    metric: str
    method: str
    tags: list[str] = Field(default_factory=list)
    evidence_id: str = ""
    source: str = ""
    role_families: list[str] = Field(default_factory=list)
    disclosure_constraints: str = ""


class FitBrief(BaseModel):
    primary_role_family: str
    secondary_role_family: str = ""
    hiring_outcomes: list[str] = Field(default_factory=list)


class KeywordMapping(BaseModel):
    keyword: str
    priority: str
    supporting_evidence: str = ""
    use_in_resume: bool = False


class SelectedEvidence(BaseModel):
    evidence_id: str = ""
    source: str = ""
    keyword: str
    bullet: str
    relevance: str
    score: float


class ResumeVariant(BaseModel):
    job_id: str
    company: str
    title: str
    keywords: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    fit_brief: FitBrief | None = None
    keyword_map: list[KeywordMapping] = Field(default_factory=list)
    selected_evidence: list[SelectedEvidence] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list)
    pagination_status: str = "two-page-targeted; final pagination requires template rendering"

    @property
    def text(self) -> str:
        return "\n".join(f"- {bullet}" for bullet in self.bullets)
