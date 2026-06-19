"""Job match scoring.

Overall match % blends two signals over the job's title + (enriched) description:
  1. TF-IDF + cosine similarity  — semantic overlap between the candidate profile
     (resume summary + target keywords) and the job text  [scikit-learn].
  2. ATS keyword match           — coverage of the candidate's hard keywords
     (primary skills, role titles, seniority) literally present in the job text.

final_score = 100 * (0.65 * overall_match + 0.35 * company_match), with an optional
recency boost for jobs posted in the last 24h. company_match weights target employers.
"""
from __future__ import annotations

import os
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import load_targets
from models import Job

_data = load_targets()

PRIMARY = {k.lower() for k in _data["keywords_for_matching"]["primary_skills"]}
SECONDARY = {k.lower() for k in _data["keywords_for_matching"]["secondary_skills"]}
ROLE_TITLES = {t.lower() for t in _data["keywords_for_matching"]["role_titles"]}
SENIORITY = {
    t.lower()
    for titles in _data["keywords_for_matching"]["seniority_titles"].values()
    for t in titles
}
TARGET_COMPANIES: dict[str, int] = {}
for _cat in _data["data_and_ai_companies"]["target_categories"].values():
    for _company in _cat["companies"]:
        TARGET_COMPANIES[_company["name"].lower().strip()] = _cat["priority"]

# Hard keywords an ATS would screen a resume against.
ATS_KEYWORDS = sorted(PRIMARY | ROLE_TITLES | SENIORITY)
# Matching this many distinct ATS keywords counts as full ATS coverage.
_ATS_FULL_COVERAGE = 10.0

# Freshness boost is config-driven (Target-list.json auto_apply_rules.time_based_boost).
RECENCY_BOOST = float(
    _data.get("auto_apply_rules", {}).get("time_based_boost", {}).get("boost_percentage", 5)
)


def _text(job: Job) -> str:
    return f"{job.title} {job.description}".lower()


@lru_cache(maxsize=1)
def _profile_doc() -> str:
    """Candidate reference document: resume summary + all target keywords.

    Lazy + cached so RESUME_SUMMARY (loaded from .env in runner.main) is picked up.
    """
    parts = [os.environ.get("RESUME_SUMMARY", "")]
    parts += sorted(PRIMARY) + sorted(SECONDARY) + sorted(ROLE_TITLES) + sorted(SENIORITY)
    return " ".join(p for p in parts if p).lower()


def title_on_allowlist(job: Job) -> bool:
    text = _text(job)
    return any(role_title in text for role_title in ROLE_TITLES)


def tfidf_similarity(job: Job) -> float:
    """Cosine similarity between the candidate profile and the job text (TF-IDF vectors)."""
    job_text = _text(job).strip()
    if not job_text:
        return 0.0
    try:
        matrix = TfidfVectorizer(stop_words="english").fit_transform([_profile_doc(), job_text])
    except ValueError:
        return 0.0  # empty vocabulary after stop-word removal
    return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])


def ats_match(job: Job) -> float:
    """ATS-style keyword coverage: fraction of hard keywords present (capped)."""
    text = _text(job)
    hits = sum(1 for k in ATS_KEYWORDS if k in text)
    return min(1.0, hits / _ATS_FULL_COVERAGE)


def overall_match(job: Job) -> float:
    """Overall match in [0, 1]: TF-IDF semantic similarity + ATS keyword match."""
    return 0.60 * tfidf_similarity(job) + 0.40 * ats_match(job)


@lru_cache(maxsize=1)
def _target_token_sets() -> tuple[tuple[frozenset[str], int], ...]:
    return tuple((frozenset(name.split()), prio) for name, prio in TARGET_COMPANIES.items())


def _target_priority(company: str) -> int | None:
    """Best (lowest) priority of any target whose name tokens are a subset of the company.

    Token-subset so "CIMB Singapore" / "OCBC Bank" still match targets "CIMB" / "OCBC".
    """
    tokens = frozenset(company.lower().split())
    best: int | None = None
    for tset, prio in _target_token_sets():
        if tset and tset <= tokens:
            best = prio if best is None else min(best, prio)
    return best


def company_match(job: Job) -> float:
    """Target-employer weighting: priority-1 targets score 1.0, others a low baseline."""
    prio = _target_priority(job.company_canonical)
    if prio is not None:
        return (10 - prio) / 9.0  # priority 1 -> 1.0
    return 0.3


def final_score(job: Job, within_24h: bool = False) -> float:
    fs = 100 * (0.65 * overall_match(job) + 0.35 * company_match(job))
    if within_24h:
        fs = min(100.0, fs + RECENCY_BOOST)
    return round(fs, 1)
