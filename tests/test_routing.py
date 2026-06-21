from models import Job
from routing import apply_tier, should_outreach


def _job(title: str, ats: str, score: float | None, company: str = "SomeCo") -> Job:
    return Job(
        id="test",
        source="test",
        company_canonical=company,
        dedupe_key=f"{company}|{title}|{ats}|{score}",
        title=title,
        url="https://example.com",
        ats_type=ats,
        score=score,
    )


def test_priority1_bank_auto_applies():
    # DBS is a priority-1 target (sg_banks); ATS type no longer matters for Tier A.
    job = _job("Head of Data", "linkedin", 70.0, company="DBS")
    assert apply_tier(job) == "A"
    assert should_outreach(job) is True


def test_priority1_bank_with_suffix_auto_applies():
    job = _job("Head of Data", "mycareersfuture", 70.0, company="OCBC Bank")
    assert apply_tier(job) == "A"


def test_non_target_high_score_is_draft_not_auto():
    # Strong score but not a priority-1 target company -> draft, never auto-apply.
    job = _job("Data Scientist", "greenhouse", 95.0, company="Random Tech Co")
    assert apply_tier(job) == "B"
    assert should_outreach(job) is True


def test_priority1_below_auto_threshold_is_draft():
    job = _job("Data Scientist", "linkedin", 58.0, company="DBS")
    assert apply_tier(job) == "B"  # >= floor (55) but < auto threshold (65)


def test_low_score():
    job = _job("Data Scientist", "greenhouse", 50.0, company="DBS")
    assert apply_tier(job) is None
    assert should_outreach(job) is False


def test_none_score():
    job = _job("Data Scientist", "greenhouse", None, company="DBS")
    assert apply_tier(job) is None
    assert should_outreach(job) is False


def _gh_job(score: float | None, company: str = "Stripe") -> Job:
    return Job(id="t", source="greenhouse", company_canonical=company, dedupe_key="k",
               title="Data Scientist", url="https://x", ats_type="greenhouse", score=score)


def test_greenhouse_source_is_tier_a():
    # Source-based Tier A: large-fintech boards qualify without being a priority-1 bank.
    assert apply_tier(_gh_job(60.0)) == "A"
    assert apply_tier(_gh_job(56.0)) == "A"  # just above the draft floor


def test_greenhouse_below_floor_not_tier_a():
    assert apply_tier(_gh_job(50.0)) is None  # below floor -> not even a draft
