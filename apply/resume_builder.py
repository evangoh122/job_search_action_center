from __future__ import annotations

import re
from collections.abc import Iterable

from apply.resume_models import (
    FitBrief,
    KeywordMapping,
    ResumeAchievement,
    ResumeVariant,
    SelectedEvidence,
)
from models import Applicant, Job
from scoring import PRIMARY, ROLE_TITLES, SECONDARY

_SPACE = re.compile(r"\s+")


def _clean(value: str) -> str:
    """Clean."""
    return _SPACE.sub(" ", value.strip())


def build_contact_header(applicant: Applicant, location: str = "Singapore") -> str:
    """Contact header for generated resumes. Includes GitHub and resume links when set."""
    parts = [applicant.name]
    contact = [
        applicant.email,
        applicant.phone,
        applicant.linkedin_url,
        applicant.github_url,
        applicant.resume_url,
        location,
    ]
    parts.append(" | ".join(item for item in contact if item))
    return "\n".join(part for part in parts if part)


def _contains_phrase(text: str, phrase: str) -> bool:
    """Contains phrase."""
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE))


_ROLE_SIGNALS = {
    "AI product management": {
        "ai product", "generative ai", "large language model", "llm", "responsible ai",
        "human-in-the-loop", "product roadmap", "product strategy",
    },
    "product management": {
        "product manager", "product management", "product strategy", "roadmap", "discovery",
        "customer research", "adoption", "commercialization",
    },
    "data science / applied AI": {
        "data scientist", "data science", "machine learning", "predictive analytics",
        "model evaluation", "feature engineering", "experimentation", "python",
    },
    "data / analytics": {
        "data analytics", "analytics", "business intelligence", "dashboard", "sql",
        "data governance", "data engineering", "kpi",
    },
}

_DOMAIN_TOKENS = {
    "analytics", "banking", "compliance", "customer", "engineering",
    "finance", "governance", "learning", "machine", "model", "portfolio", "product",
    "risk", "strategy", "transformation",
}


def _phrase_hits(text: str, phrases: Iterable[str]) -> list[str]:
    """Phrase hits."""
    return [phrase for phrase in phrases if _contains_phrase(text, phrase)]


def classify_role(job: Job) -> tuple[str, str]:
    """Classify a vacancy into one coherent primary and optional secondary role family."""
    text = f"{job.title} {job.description}".lower()
    scores = {family: len(_phrase_hits(text, signals)) for family, signals in _ROLE_SIGNALS.items()}
    ordered = sorted(scores, key=lambda family: (-scores[family], list(_ROLE_SIGNALS).index(family)))
    primary = ordered[0] if scores[ordered[0]] else "data / analytics"
    secondary = ordered[1] if scores[ordered[1]] and scores[ordered[1]] >= scores[primary] / 2 else ""
    return primary, secondary


def _fit_brief(job: Job, keywords: list[str]) -> FitBrief:
    """Fit brief."""
    primary, secondary = classify_role(job)
    outcomes = [f"Deliver {keyword} outcomes" for keyword in keywords[:3]]
    if not outcomes:
        outcomes = [f"Deliver the core outcomes of the {job.title} role"]
    return FitBrief(
        primary_role_family=primary,
        secondary_role_family=secondary,
        hiring_outcomes=outcomes,
    )


def _achievement_keywords_for_job(job: Job, achievements: Iterable[ResumeAchievement]) -> list[str]:
    """Achievement keywords for job."""
    text = f"{job.title} {job.description}".lower()
    keywords: list[str] = []
    for achievement in achievements:
        keyword = achievement.keyword.lower()
        if keyword not in keywords and _contains_phrase(text, keyword):
            keywords.append(keyword)
    return keywords


def select_resume_keywords(job: Job, limit: int = 8) -> list[str]:
    """Pick job-relevant resume keywords, prioritizing core skills over generic role titles."""
    text = f"{job.title} {job.description}".lower()
    ordered_groups = [PRIMARY, SECONDARY, ROLE_TITLES]
    selected: list[str] = []
    for group in ordered_groups:
        for keyword in sorted(group):
            if keyword not in selected and _contains_phrase(text, keyword):
                selected.append(keyword)
                if len(selected) >= limit:
                    return selected
    return selected


def _achievement_score(
    achievement: ResumeAchievement,
    keywords: Iterable[str],
    job_text: str,
) -> tuple[float, int, str, str] | None:
    """Apply the evidence rubric from the resume-agent specification.

    Evidence with no outcome/domain/method connection is excluded. This prevents a shared generic
    tool from pulling an unrelated achievement into the resume.
    """
    haystack = " ".join(
        [achievement.keyword, achievement.result, achievement.metric, achievement.method, *achievement.tags]
    ).lower()
    best_index = 10_000
    best_keyword = achievement.keyword
    score = 0.0
    reasons: list[str] = []
    labels = [achievement.keyword, *achievement.tags]
    direct = _contains_phrase(job_text, achievement.keyword)
    matched_required: list[str] = []
    matched_preferred: list[str] = []
    for index, keyword in enumerate(keywords):
        if _contains_phrase(haystack, keyword):
            if keyword in PRIMARY or keyword in ROLE_TITLES:
                matched_required.append(keyword)
                weight = 3
            else:
                matched_preferred.append(keyword)
                weight = 1
            if weight > 0 and index < best_index:
                best_index = index
                best_keyword = keyword
    contextual = [label for label in labels if _contains_phrase(job_text, label)]
    if not contextual:
        job_tokens = set(re.findall(r"[a-z][a-z-]+", job_text))
        for label in labels:
            shared = set(re.findall(r"[a-z][a-z-]+", label.lower())) & job_tokens & _DOMAIN_TOKENS
            if shared:
                contextual.append(next(iter(sorted(shared))))
                break
    if direct:
        score += 4
        reasons.append("directly matches a job outcome or capability")
        best_keyword = achievement.keyword
    if matched_required:
        score += 3
        reasons.append(f"supports required capability: {matched_required[0]}")
    if contextual and not direct:
        score += 2
        reasons.append(f"matches job domain or method: {contextual[0]}")
    if matched_preferred:
        score += 1
        reasons.append(f"supports preferred capability: {matched_preferred[0]}")
    if achievement.metric.strip():
        score += 2
        reasons.append("contains a verified measurement or scope")
    ownership = re.search(
        r"\b(led|owned|launched|built|developed|created|implemented|"
        r"productiz(?:e|es|ed|ing)|dr(?:ive|ives|iving|ove|iven))\b",
        f"{achievement.result} {achievement.method}",
        re.IGNORECASE,
    )
    if ownership:
        score += 2
        reasons.append("shows explicit delivery ownership")
    if not (direct or matched_required or matched_preferred or contextual):
        return None
    return -score, best_index, best_keyword, "; ".join(reasons)


def _exact_master_block(keyword: str, achievement: ResumeAchievement) -> str:
    """Return the authoritative block verbatim; never compose application claims."""
    del keyword
    return achievement.block_text


def build_resume_variant(
    job: Job,
    achievements: list[ResumeAchievement],
    keyword_limit: int = 8,
    bullet_limit: int = 6,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
) -> ResumeVariant:
    """Build a targeted excerpt by selecting and reordering exact master-resume blocks.

    XYZ fields inform relevance only. They are never rendered into application copy. Evidence
    lacking exact master-resume text, provenance, or an intact hash is rejected fail-closed.
    """
    selected = select_resume_keywords(job, limit=keyword_limit)
    achievement_keywords = _achievement_keywords_for_job(job, achievements)
    keywords = (selected + [k for k in achievement_keywords if k not in selected])[:keyword_limit]
    job_text = f"{job.title} {job.description}".lower()
    ranked: list[tuple[float, int, str, ResumeAchievement, str]] = []
    for achievement in achievements:
        if not achievement.has_verified_master_block():
            continue
        if achievement.disclosure_constraints.strip():
            continue
        labels = {achievement.keyword.lower(), *(tag.lower() for tag in achievement.tags)}
        if include_tags and not (labels & {tag.lower() for tag in include_tags}):
            continue
        if exclude_tags and (labels & {tag.lower() for tag in exclude_tags}):
            continue
        if not (achievement.result.strip() and achievement.metric.strip() and achievement.method.strip()):
            continue
        scored = _achievement_score(achievement, keywords, job_text)
        if scored is None:
            continue
        score, rank, keyword, relevance = scored
        ranked.append((score, rank, keyword, achievement, relevance))

    ranked.sort(key=lambda item: (item[0], item[1], item[3].keyword.lower()))
    bullets = [
        _exact_master_block(keyword, achievement)
        for _, _, keyword, achievement, _ in ranked[:bullet_limit]
    ]
    selected_rows = [
        SelectedEvidence(
            evidence_id=achievement.evidence_id,
            source=achievement.source,
            provenance=achievement.provenance,
            block_hash=achievement.block_hash,
            keyword=keyword,
            bullet=_exact_master_block(keyword, achievement),
            relevance=relevance,
            score=-score,
        )
        for score, _, keyword, achievement, relevance in ranked[:bullet_limit]
    ]
    keyword_map: list[KeywordMapping] = []
    for keyword in keywords:
        evidence = next(
            (
                row
                for row in selected_rows
                if _contains_phrase(row.bullet, keyword)
            ),
            None,
        )
        keyword_map.append(
            KeywordMapping(
                keyword=keyword,
                priority="required" if keyword in PRIMARY or keyword in ROLE_TITLES else "preferred",
                supporting_evidence=evidence.bullet if evidence else "unsupported by selected evidence",
                use_in_resume=evidence is not None,
            )
        )
    gaps = [
        f"Unsupported {mapping.priority} keyword in selected evidence: {mapping.keyword}"
        for mapping in keyword_map
        if not mapping.use_in_resume
    ]
    change_log = [
        "Selected and reordered exact master-resume blocks using job-outcome, capability, domain, measurement, and ownership evidence.",
        "Rejected evidence without verbatim block text, master-resume provenance, or a matching SHA-256 hash.",
        "Preserved every selected block byte-for-byte; no application bullet was rewritten or synthesized.",
    ]
    return ResumeVariant(
        job_id=job.id,
        company=job.company_canonical,
        title=job.title,
        keywords=keywords,
        bullets=bullets,
        fit_brief=_fit_brief(job, keywords),
        keyword_map=keyword_map,
        selected_evidence=selected_rows,
        evidence_gaps=gaps,
        change_log=change_log,
    )
