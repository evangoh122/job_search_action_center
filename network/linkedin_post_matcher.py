"""Find LinkedIn feed posts that refer to a known vacancy.

Uses a separate Apify post-search actor. Results are evidence-bearing review candidates;
this module never sends messages or treats an ambiguous post as authoritative.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256

import httpx

from matching import normalize_company, normalize_title
from models import Job, LinkedInPostMatch
from network.email_finder import _classify

logger = logging.getLogger(__name__)

_ACTOR = "harvestapi~linkedin-post-search"
_RUN_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
_JOB_ID = re.compile(r"(?:/jobs/view/(?:[^/?#]*-)?|currentJobId=)(\d{6,})", re.I)
_HIRING = re.compile(r"\b(hiring|vacancy|opening|join (?:my|our) team|apply|role)\b", re.I)
_REFERRAL = re.compile(
    r"\b(happy to refer|can refer|offer(?:ing)? referrals?|referrals? available|"
    r"DM me (?:for|about) (?:a )?referral|reach out (?:for|about) (?:a )?referral|"
    r"message me (?:for|about) (?:a )?referral)\b",
    re.I,
)
HttpPost = Callable[[str, dict], list | dict]


def linkedin_job_ids(job: Job) -> set[str]:
    """Linkedin job ids."""
    values = {job.url, *job.source_urls.values()}
    return {match.group(1) for value in values for match in _JOB_ID.finditer(value or "")}


def _tokens(value: str) -> set[str]:
    """Tokens."""
    return set(re.findall(r"[a-z0-9]+", normalize_title(value)))


def _similarity(left: str, right: str) -> float:
    """Similarity."""
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a | b else 0.0


def _coverage(needle: str, haystack: str) -> float:
    """Coverage."""
    expected, observed = _tokens(needle), _tokens(haystack)
    return len(expected & observed) / len(expected) if expected else 0.0


def _post_date(value: object) -> datetime | None:
    """Post date."""
    if isinstance(value, dict):
        value = value.get("date") or value.get("timestamp")
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value)
        if value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except (OSError, TypeError, ValueError):
        pass
    return None


def score_post(job: Job, item: dict) -> LinkedInPostMatch | None:
    """Score post."""
    text = str(item.get("content") or item.get("text") or item.get("commentary") or "").strip()
    post_url = str(item.get("linkedinUrl") or item.get("postUrl") or item.get("url") or "").strip()
    if not text or not post_url:
        return None
    serialized = json.dumps(item, ensure_ascii=False)
    source_urls = {value for value in (job.url, *job.source_urls.values()) if value}
    ids = linkedin_job_ids(job)
    exact_url = any(url in serialized for url in source_urls)
    exact_id = any(job_id in serialized for job_id in ids)

    title_score = _coverage(job.title, text)
    company_tokens = set(normalize_company(job.company_canonical).split())
    text_tokens = _tokens(text)
    company_in_text = bool(company_tokens) and company_tokens <= text_tokens
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    author_info = str(author.get("info") or author.get("headline") or "")
    author_company = _coverage(job.company_canonical, author_info) >= 0.75
    hiring = bool(_HIRING.search(text))
    referral_offer = bool(_REFERRAL.search(text))

    evidence: list[str] = []
    if exact_url:
        evidence.append("exact_job_url")
    if exact_id:
        evidence.append("exact_linkedin_job_id")
    if company_in_text:
        evidence.append("company_in_post")
    if author_company:
        evidence.append("company_in_author_profile")
    if title_score >= 0.5:
        evidence.append(f"title_similarity:{title_score:.2f}")
    if hiring:
        evidence.append("hiring_language")
    if referral_offer:
        evidence.append("referral_offer_language")

    if exact_url or exact_id:
        confidence = 1.0
    else:
        company_signal = company_in_text or author_company
        if not company_signal or title_score < 0.55 or not (hiring or referral_offer):
            return None
        confidence = min(0.94, 0.58 * title_score + 0.20
                         + (0.10 if hiring or referral_offer else 0)
                         + (0.06 if company_in_text and author_company else 0))
        if confidence < 0.72:
            return None

    author_name = str(author.get("name") or item.get("authorName") or "")
    author_profile = str(author.get("linkedinUrl") or item.get("authorProfileUrl") or "")
    author_role = _classify(author_info, "") or ""
    post_id = str(item.get("id") or sha256(post_url.encode()).hexdigest()[:20])
    return LinkedInPostMatch(
        id=f"{job.id}|{post_id}", job_id=job.id, job_key=job.dedupe_key,
        company=job.company_canonical, job_title=job.title, job_url=job.url,
        post_url=post_url, post_text=text, posted_at=_post_date(item.get("postedAt")),
        author_name=author_name, author_title=author_info,
        author_profile_url=author_profile, author_role_type=author_role,
        confidence=round(confidence, 4), evidence=evidence,
        post_intent=("both" if hiring and referral_offer else
                     "referral_offer" if referral_offer else "hiring"),
    )


class LinkedInPostMatcher:
    """Represent linked in post matcher."""
    def __init__(self, token: str, *, max_posts: int = 10, posted_limit: str = "week",
                 http_post: HttpPost | None = None) -> None:
        """Initialize the instance."""
        self.token = token
        self.max_posts = max(1, min(max_posts, 50))
        self.posted_limit = posted_limit
        self.http_post = http_post or self._default_post

    def _default_post(self, url: str, body: dict) -> list:
        """Default post."""
        response = httpx.post(url, json=body, timeout=180)
        response.raise_for_status()
        value = response.json()
        return value if isinstance(value, list) else value.get("items") or value.get("data") or []

    @staticmethod
    def queries(job: Job) -> list[str]:
        # Actor documentation states that LinkedIn limits a query to 85 characters.
        """Queries."""
        title_query = f'"{job.title[:83]}"'
        # A pasted LinkedIn job ID is the strongest discoverable cross-reference.
        referral_query = f'referral "{job.title[:74]}"'
        return list(dict.fromkeys([
            title_query, referral_query[:85], *sorted(linkedin_job_ids(job)),
        ]))

    def find_matches(self, job: Job) -> list[LinkedInPostMatch]:
        """Find matches."""
        url = _RUN_URL.format(actor=_ACTOR, token=self.token)
        body = {
            "searchQueries": self.queries(job), "postedLimit": self.posted_limit,
            "sortBy": "date", "maxPosts": self.max_posts,
            "scrapeComments": False, "scrapeReactions": False,
        }
        try:
            response = self.http_post(url, body)
        except Exception:
            logger.warning("LinkedIn post search failed for %s", job.dedupe_key, exc_info=True)
            return []
        items = response if isinstance(response, list) else response.get("items") or response.get("data") or []
        matches = [match for item in items if isinstance(item, dict)
                   if (match := score_post(job, item)) is not None]
        return sorted(matches, key=lambda match: match.confidence, reverse=True)
