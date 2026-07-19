from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field, model_validator


MASTER_RESUME_PROVENANCE = "master resume"


def resume_block_hash(block_text: str) -> str:
    """Return the SHA-256 fingerprint of an exact master-resume block."""
    return hashlib.sha256(block_text.encode("utf-8")).hexdigest()


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
    block_text: str = ""
    provenance: str = ""
    block_hash: str = ""
    role_families: list[str] = Field(default_factory=list)
    disclosure_constraints: str = ""

    @model_validator(mode="after")
    def populate_exact_block_metadata(self) -> ResumeAchievement:
        """Fill only metadata that can be derived without changing resume content.

        ``source="master resume"`` is the sole legacy provenance bridge. Structured XYZ
        fields are deliberately never rendered back into a block: they are useful for
        ranking, but they are not an authoritative copy of the master resume.
        """
        if not self.provenance and self.source.strip().casefold() == MASTER_RESUME_PROVENANCE:
            self.provenance = MASTER_RESUME_PROVENANCE
        if self.block_text and not self.block_hash:
            self.block_hash = resume_block_hash(self.block_text)
        return self

    def has_verified_master_block(self) -> bool:
        """Whether this evidence is an untampered, exact master-resume block."""
        return bool(
            self.block_text
            and self.provenance.strip().casefold() == MASTER_RESUME_PROVENANCE
            and self.block_hash == resume_block_hash(self.block_text)
        )


class FitBrief(BaseModel):
    """Represent fit brief."""
    primary_role_family: str
    secondary_role_family: str = ""
    hiring_outcomes: list[str] = Field(default_factory=list)


class KeywordMapping(BaseModel):
    """Represent keyword mapping."""
    keyword: str
    priority: str
    supporting_evidence: str = ""
    use_in_resume: bool = False


class SelectedEvidence(BaseModel):
    """Represent selected evidence."""
    evidence_id: str = ""
    source: str = ""
    provenance: str = ""
    block_hash: str = ""
    keyword: str
    bullet: str
    relevance: str
    score: float


class ResumeVariant(BaseModel):
    """Represent resume variant."""
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
        """Text."""
        return "\n".join(f"- {bullet}" for bullet in self.bullets)
