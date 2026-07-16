from __future__ import annotations

from unittest.mock import Mock, patch

from network.linkedin_poster import LinkedInPosterFinder


def _http(items: list):
    def _post(url: str, body: dict) -> list:
        return items
    return _post


def test_find_poster_returns_recruiter_contact():
    items = [{
        "jobPosterName": "Jane Doe",
        "jobPosterTitle": "Technical Recruiter",
        "jobPosterProfileUrl": "https://linkedin.com/in/jane",
        "companyName": "Acme",
    }]
    c = LinkedInPosterFinder("fake", http_post=_http(items)).find_poster("https://x/123", company="Acme")
    assert c is not None
    assert c.name == "Jane Doe"
    assert c.role_type == "recruiter"
    assert c.linkedin_url == "https://linkedin.com/in/jane"
    assert c.email == ""


def test_manager_classified_as_hiring_manager():
    items = [{"jobPosterName": "Sam Lee", "jobPosterTitle": "Engineering Manager",
              "jobPosterProfileUrl": "https://linkedin.com/in/sam", "companyName": "Acme"}]
    c = LinkedInPosterFinder("fake", http_post=_http(items)).find_poster("https://x/123")
    assert c is not None
    assert c.role_type == "hiring_manager"


def test_items_without_poster_name_skipped():
    items = [
        {"jobPosterTitle": "Technical Recruiter", "companyName": "Acme"},
        {"jobPosterName": None, "companyName": "Acme"},
        {"companyName": "Acme"},
    ]
    assert LinkedInPosterFinder("fake", http_post=_http(items)).find_poster("https://x/123") is None


def test_exception_returns_none():
    def _fail(url: str, body: dict) -> list:
        raise RuntimeError("network error")

    assert LinkedInPosterFinder("fake", http_post=_fail).find_poster("https://x/123") is None


def test_default_post_uses_bearer_header_not_query_parameter():
    """Keep the Apify token out of URLs and request logs."""
    response = Mock()
    response.json.return_value = []
    with patch("network.linkedin_poster.httpx.post", return_value=response) as post:
        LinkedInPosterFinder("secret-token").find_poster("https://x/123")

    url = post.call_args.args[0]
    assert "token=" not in url
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret-token"}
