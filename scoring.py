from __future__ import annotations

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

# Freshness boost is config-driven (Target-list.json auto_apply_rules.time_based_boost).
RECENCY_BOOST = float(
    _data.get("auto_apply_rules", {}).get("time_based_boost", {}).get("boost_percentage", 5)
)


def _text(job: Job) -> str:
    return f"{job.title} {job.description}".lower()


def title_on_allowlist(job: Job) -> bool:
    text = _text(job)
    return any(role_title in text for role_title in ROLE_TITLES)


def skills_match(job: Job) -> float:
    text = _text(job)
    p = sum(1 for k in PRIMARY if k in text)
    s = sum(1 for k in SECONDARY if k in text)
    primary_cov = min(1.0, p / 5.0)
    secondary_cov = min(1.0, s / 5.0)
    exp = 1.0 if any(t in text for t in SENIORITY) else 0.5
    industry = 1.0 if job.company_canonical.lower().strip() in TARGET_COMPANIES else 0.4
    return 0.50 * primary_cov + 0.25 * secondary_cov + 0.15 * exp + 0.10 * industry


def company_match(job: Job) -> float:
    text = _text(job)
    key = job.company_canonical.lower().strip()
    is_target = key in TARGET_COMPANIES
    name_match = 1.0 if is_target else 0.0
    category_priority = (10 - TARGET_COMPANIES[key]) / 9.0 if is_target else 0.3
    role_match = 1.0 if any(r in text for r in ROLE_TITLES) else 0.0
    seniority_match = 1.0 if any(t in text for t in SENIORITY) else 0.4
    p = sum(1 for k in PRIMARY if k in text)
    keyword_density = min(1.0, p / 5.0)
    return (
        0.15 * category_priority
        + 0.15 * name_match
        + 0.30 * seniority_match
        + 0.25 * role_match
        + 0.15 * keyword_density
    )


def final_score(job: Job, within_24h: bool = False) -> float:
    fs = 100 * (0.65 * skills_match(job) + 0.35 * company_match(job))
    if within_24h:
        fs = min(100.0, fs + RECENCY_BOOST)
    return round(fs, 1)
