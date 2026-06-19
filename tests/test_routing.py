from models import Job
from routing import apply_tier, should_outreach


def _job(title: str, ats: str, score: float | None) -> Job:
    return Job(
        id="test",
        source="test",
        company_canonical="SomeCo",
        dedupe_key=f"someco|{title}|{ats}|{score}",
        title=title,
        url="https://example.com",
        ats_type=ats,
        score=score,
    )


def test_auto_apply_greenhouse():
    job = _job("Head of Data", "greenhouse", 95.0)  # title in VP/leadership allowlist
    assert apply_tier(job) == "A"
    assert should_outreach(job) is True


def test_non_simple_ats_never_auto():
    job = _job("Data Scientist", "mycareersfuture", 95.0)
    assert apply_tier(job) == "B"  # login-wall ATS -> draft, never auto
    assert should_outreach(job) is True


def test_draft_tier():
    job = _job("Data Scientist", "lever", 80.0)
    assert apply_tier(job) == "B"
    assert should_outreach(job) is True


def test_low_score():
    job = _job("Data Scientist", "greenhouse", 50.0)
    assert apply_tier(job) is None
    assert should_outreach(job) is False


def test_none_score():
    job = _job("Data Scientist", "greenhouse", None)
    assert apply_tier(job) is None
    assert should_outreach(job) is False
