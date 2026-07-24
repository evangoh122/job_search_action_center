from __future__ import annotations

from datetime import datetime, timedelta

from sources.greenhouse import GreenhouseSource

_RECENT = (datetime.now() - timedelta(days=1)).isoformat() + "Z"
_OLD = (datetime.now() - timedelta(days=60)).isoformat() + "Z"


def _board_jobs():
    """Provide a test helper for board jobs."""
    return {
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true": {"jobs": [
            {"title": "Head of Data Platform", "absolute_url": "https://x/1",
             "updated_at": _RECENT, "location": {"name": "Singapore"},
             "content": "Build &amp; lead <b>machine learning</b> teams"},
            {"title": "Senior Frontend Engineer", "absolute_url": "https://x/2",
             "updated_at": _RECENT, "location": {"name": "Singapore"}, "content": "React"},
            {"title": "Data Scientist", "absolute_url": "https://x/3",
             "updated_at": _RECENT, "location": {"name": "Dublin"}, "content": "stats"},
            {"title": "Analytics Lead", "absolute_url": "https://x/4",
             "updated_at": _OLD, "location": {"name": "Singapore"}, "content": "old role"},
        ]},
    }


def _fake_get(mapping):
    """Provide a test helper for fake get."""
    def get(url: str) -> dict:
        """Provide a test helper for get."""
        return mapping.get(url, {"jobs": []})
    return get


def test_filters_by_title_keyword():
    """Verify filtering by title keyword."""
    src = GreenhouseSource(boards={"stripe": "Stripe"}, http_get=_fake_get(_board_jobs()))
    jobs = src.fetch()
    titles = {j.title for j in jobs}
    assert "Head of Data Platform" in titles
    assert "Senior Frontend Engineer" not in titles  # no data/AI keyword


def test_location_filter():
    """Verify the location filter scenario."""
    src = GreenhouseSource(boards={"stripe": "Stripe"}, location_contains="Singapore",
                           http_get=_fake_get(_board_jobs()))
    titles = {j.title for j in src.fetch()}
    assert "Data Scientist" not in titles  # Dublin filtered out
    assert "Head of Data Platform" in titles


def test_age_cutoff():
    """Verify the age cutoff scenario."""
    src = GreenhouseSource(boards={"stripe": "Stripe"}, max_age_days=7,
                           http_get=_fake_get(_board_jobs()))
    titles = {j.title for j in src.fetch()}
    assert "Analytics Lead" not in titles  # 60 days old


def test_maps_fields_and_strips_html():
    """Verify mapping fields and strips html."""
    src = GreenhouseSource(boards={"stripe": "Stripe"}, location_contains="Singapore",
                           http_get=_fake_get(_board_jobs()))
    job = next(j for j in src.fetch() if j.title == "Head of Data Platform")
    assert job.source == "greenhouse"
    assert job.company == "Stripe"
    assert job.ats_type == "greenhouse"
    assert job.url == "https://x/1"
    assert job.posted_at is not None and job.posted_at.tzinfo is None  # naive, pipeline-safe
    assert "Build & lead machine learning teams" == job.description  # unescaped + tags stripped


def test_bad_board_is_skipped():
    """Verify the bad board is skipped scenario."""
    def boom(url: str) -> dict:
        """Provide a test helper for boom."""
        raise RuntimeError("404")
    src = GreenhouseSource(boards={"nope": "Nope"}, http_get=boom)
    assert src.fetch() == []  # failure logged, not raised
