"""Conservative cross-board identity matching for job listings.

Job-board URLs are deliberately excluded from the identity key: LinkedIn,
MyCareersFuture, and eFinancialCareers often advertise the same vacancy with
different URLs. The key uses normalized company and title text instead.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from models import Job
from salary import SalaryRange, aggregate_salary
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_COMPANY_SUFFIXES = {
    "limited", "ltd", "pte", "private", "inc", "incorporated", "llc",
    "plc", "corp", "corporation", "company", "co",
}


def _words(value: str) -> list[str]:
    """Words."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"\bsenior[\s-]+vice[\s-]+president\b", "svp", value)
    value = re.sub(r"\bfirst[\s-]+vice[\s-]+president\b", "fvp", value)
    value = re.sub(r"\bvice[\s-]+president\b", "vp", value)
    return re.findall(r"[a-z0-9]+", value)


def normalize_company(value: str) -> str:
    """Normalize company."""
    words = _words(value)
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_title(value: str) -> str:
    """Normalize title."""
    return " ".join(_words(value))


def job_identity_key(company: str, title: str) -> str:
    """Return a stable, readable cross-source vacancy key."""
    return f"{normalize_company(company)}|{normalize_title(title)}"


def merge_jobs(existing: Job, incoming: Job) -> Job:
    """Merge board provenance while preserving the user's workflow state."""
    merged = existing.model_copy(deep=True)
    merged.sources = list(dict.fromkeys([
        *(existing.sources or [existing.source]),
        *(incoming.sources or [incoming.source]),
    ]))
    urls = dict(existing.source_urls)
    urls.setdefault(existing.source, existing.url)
    urls.update(incoming.source_urls)
    urls.setdefault(incoming.source, incoming.url)
    merged.source_urls = urls

    if len(incoming.description or "") > len(existing.description or ""):
        merged.description = incoming.description
    if existing.posted_at is None or (
        incoming.posted_at is not None and incoming.posted_at < existing.posted_at
    ):
        merged.posted_at = incoming.posted_at
    if merged.score is None:
        merged.score = incoming.score
    if merged.tier is None:
        merged.tier = incoming.tier
    salary = aggregate_salary(
        SalaryRange(existing.salary_min, existing.salary_max,
                    existing.salary_currency, existing.salary_period),
        SalaryRange(incoming.salary_min, incoming.salary_max,
                    incoming.salary_currency, incoming.salary_period),
    )
    merged.salary_min = salary.minimum
    merged.salary_max = salary.maximum
    merged.salary_average = salary.average
    merged.salary_currency = salary.currency
    merged.salary_period = salary.period
    return merged


def find_duplicate_job(incoming: Job, jobs: list[Job]) -> Job | None:
    """Find a cross-platform duplicate using title and substantive description.

    Exact canonical keys remain the strongest signal. Fuzzy automatic merging requires
    both a very similar title and a highly similar full description, avoiding broad
    keyword-only merges between different vacancies.
    """
    for job in jobs:
        if job.dedupe_key == incoming.dedupe_key:
            return job
    if len(_description_core(incoming.description)) < 250:
        return None
    candidates = [job for job in jobs if not set(job.sources or [job.source])
                  & set(incoming.sources or [incoming.source])]
    matches = rank_description_matches([*candidates, incoming], limit=len(candidates))
    for match in matches:
        if incoming not in (match.left, match.right):
            continue
        if match.title_similarity >= 0.82 and (
            match.description_similarity >= 0.72 or match.phrase_overlap >= 0.35
        ):
            return match.right if match.left is incoming else match.left
    return None


@dataclass(frozen=True)
class DescriptionMatch:
    """Represent description match."""
    left: Job
    right: Job
    description_similarity: float
    phrase_overlap: float
    title_similarity: float
    company_similarity: float
    confidence: float


def _token_similarity(left: str, right: str) -> float:
    """Token similarity."""
    a, b = set(_words(left)), set(_words(right))
    return len(a & b) / len(a | b) if a | b else 0.0


def _description_core(value: str) -> str:
    """Remove common trailing employer/EEO boilerplate before comparison."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()
    boilerplate = re.search(
        r"\b(about (?:us|the company)|equal opportunity|diversity and inclusion|"
        r"privacy notice|personal data protection|how to apply)\b",
        text,
        flags=re.IGNORECASE,
    )
    return (text[:boilerplate.start()] if boilerplate else text).strip()


def _word_ngrams(value: str, size: int = 4) -> set[tuple[str, ...]]:
    """Word ngrams."""
    words = _words(value)
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def find_description_matches(
    jobs: list[Job],
    *,
    min_description_chars: int = 250,
    min_description_similarity: float = 0.62,
    min_confidence: float = 0.72,
) -> list[DescriptionMatch]:
    """Find likely cross-board duplicates from responsibilities and requirements.

    Results are candidates for human review, not automatic merges. Character n-grams
    tolerate formatting and small wording changes while remaining stricter than broad
    keyword/topic similarity.
    """
    eligible = [
        job for job in jobs
        if len(_description_core(job.description)) >= min_description_chars
    ]
    if len(eligible) < 2:
        return []
    documents = [_description_core(job.description) for job in eligible]
    phrase_sets = [_word_ngrams(document) for document in documents]
    try:
        matrix = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(4, 5),
            min_df=1,
            sublinear_tf=True,
            max_features=40_000,
        ).fit_transform(documents)
    except ValueError:
        return []
    similarities = cosine_similarity(matrix)
    matches: list[DescriptionMatch] = []
    for i, left in enumerate(eligible):
        left_sources = set(left.sources or [left.source])
        for j in range(i + 1, len(eligible)):
            right = eligible[j]
            if left_sources & set(right.sources or [right.source]):
                continue
            description_score = float(similarities[i, j])
            shared_phrases = len(phrase_sets[i] & phrase_sets[j])
            phrase_overlap = (
                shared_phrases / min(len(phrase_sets[i]), len(phrase_sets[j]))
                if phrase_sets[i] and phrase_sets[j] else 0.0
            )
            title_score = _token_similarity(left.title, right.title)
            company_score = _token_similarity(
                normalize_company(left.company_canonical),
                normalize_company(right.company_canonical),
            )
            confidence = (
                0.55 * description_score + 0.25 * phrase_overlap
                + 0.12 * title_score + 0.08 * company_score
            )
            # Very close/copy-pasted write-ups are candidates even when a recruiter is
            # shown as the MCF company and the end employer is shown on LinkedIn.
            copied_section = phrase_overlap >= 0.45
            exact_title_with_shared_detail = (
                title_score >= 0.90 and phrase_overlap >= 0.12 and description_score >= 0.25
            )
            if (
                description_score < min_description_similarity
                and not copied_section
                and not exact_title_with_shared_detail
            ):
                continue
            if (
                description_score < 0.82
                and confidence < min_confidence
                and not copied_section
                and not exact_title_with_shared_detail
            ):
                continue
            matches.append(DescriptionMatch(
                left=left,
                right=right,
                description_similarity=description_score,
                phrase_overlap=phrase_overlap,
                title_similarity=title_score,
                company_similarity=company_score,
                confidence=confidence,
            ))
    return sorted(matches, key=lambda match: match.confidence, reverse=True)


def rank_description_matches(jobs: list[Job], limit: int = 10) -> list[DescriptionMatch]:
    """Return the closest cross-board write-ups, even when none is a likely duplicate."""
    return find_description_matches(
        jobs,
        min_description_similarity=0.0,
        min_confidence=0.0,
    )[:limit]
