from models import Job
from network.linkedin_post_matcher import LinkedInPostMatcher, linkedin_job_ids, score_post


def _job():
    return Job(
        id="j1", source="linkedin", company_canonical="Acme Bank",
        dedupe_key="acme bank|vp data platform", title="VP Data Platform",
        url="https://www.linkedin.com/jobs/view/vp-data-platform-4321098765",
        source_urls={"linkedin": "https://www.linkedin.com/jobs/view/4321098765"},
    )


def _item(content, **changes):
    value = {
        "id": "post1", "linkedinUrl": "https://linkedin.com/posts/jane-activity-123",
        "content": content,
        "author": {"name": "Jane Tan", "linkedinUrl": "https://linkedin.com/in/jane",
                   "info": "Head of Data at Acme Bank"},
        "postedAt": {"date": "2026-07-15T01:00:00Z"},
    }
    value.update(changes)
    return value


def test_exact_job_link_is_certain_even_with_short_post():
    item = _item("We are hiring — details here", attachments=[{
        "url": "https://www.linkedin.com/jobs/view/4321098765"}])
    match = score_post(_job(), item)
    assert match is not None
    assert match.confidence == 1.0
    assert "exact_linkedin_job_id" in match.evidence
    assert match.author_name == "Jane Tan"


def test_title_company_and_hiring_language_create_review_candidate():
    match = score_post(
        _job(), _item("Acme Bank is hiring a VP Data Platform to join our team."))
    assert match is not None
    assert 0.72 <= match.confidence < 1.0
    assert "company_in_post" in match.evidence
    assert any(value.startswith("title_similarity:") for value in match.evidence)


def test_generic_company_post_does_not_match_vacancy():
    assert score_post(_job(), _item("Acme Bank published its annual report.")) is None


def test_explicit_referral_offer_is_classified_separately():
    match = score_post(
        _job(), _item("Acme Bank has a VP Data Platform opening. Happy to refer qualified people."))
    assert match is not None
    assert match.post_intent == "both"
    assert "referral_offer_language" in match.evidence


def test_job_id_extraction_accepts_slug_and_plain_urls():
    assert linkedin_job_ids(_job()) == {"4321098765"}


def test_actor_request_is_bounded_and_uses_documented_fields():
    calls = []
    matcher = LinkedInPostMatcher(
        "token", max_posts=7,
        http_post=lambda url, body: calls.append((url, body)) or [
            _item("Acme Bank is hiring a VP Data Platform to join our team.")],
    )
    assert matcher.find_matches(_job())
    url, body = calls[0]
    assert "harvestapi~linkedin-post-search" in url
    assert "token=" not in url
    assert body["maxPosts"] == 7
    assert body["postedLimit"] == "week"
    assert body["scrapeComments"] is False and body["scrapeReactions"] is False
    assert all(len(query) <= 85 for query in body["searchQueries"])
    assert "4321098765" in body["searchQueries"]
    assert any(query.startswith("referral ") for query in body["searchQueries"])


def test_long_title_query_remains_balanced_and_within_actor_limit():
    job = _job()
    job.title = "Very " * 40
    query = LinkedInPostMatcher.queries(job)[0]
    assert len(query) <= 85
    assert query.startswith('"') and query.endswith('"')
