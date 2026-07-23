from datetime import date

from okr.strategy import StrategyContext, strategy_for_week


def test_august_10_checkpoint_diagnoses_zero_interviews_by_explicit_date():
    before = strategy_for_week(date(2026, 8, 3), StrategyContext())
    checkpoint = strategy_for_week(date(2026, 8, 10), StrategyContext())
    healthy = strategy_for_week(
        date(2026, 8, 10), StrategyContext(interviews_landed=1)
    )
    assert "diagnose_targeting_or_resume" not in before.pivots
    assert "diagnose_targeting_or_resume" in checkpoint.pivots
    assert "diagnose_targeting_or_resume" not in healthy.pivots


def test_august_31_shifts_saturday_afternoon_fully_to_mocks():
    strategy = strategy_for_week(date(2026, 8, 31), StrategyContext(interviews_landed=1))
    saturday = [block for block in strategy.schedule if block.day.weekday() == 5]
    assert any(block.kind == "mock_interview" and block.minutes == 225 for block in saturday)
    assert not any(block.kind == "mock_and_sourcing" for block in saturday)


def test_september_21_conditional_referral_pivot_halves_applications():
    pivoted = strategy_for_week(
        date(2026, 9, 21), StrategyContext(interviews_landed=1, offers_in_play=0)
    )
    not_pivoted = strategy_for_week(
        date(2026, 9, 21), StrategyContext(interviews_landed=1, offers_in_play=1)
    )
    assert pivoted.effective_targets.targeted_applications == 5
    assert any(block.kind == "referrals" for block in pivoted.schedule)
    assert not_pivoted.effective_targets.targeted_applications == 10
    assert not any(block.kind == "referrals" for block in not_pivoted.schedule)


def test_october_12_is_pipeline_only_even_when_offer_is_in_play():
    strategy = strategy_for_week(
        date(2026, 10, 12), StrategyContext(interviews_landed=2, offers_in_play=1)
    )
    assert strategy.effective_targets.targeted_applications == 0
    assert "pipeline_closing_only" in strategy.pivots
    assert len([block for block in strategy.schedule if block.kind == "pipeline_closing"]) == 2
    assert not any(block.kind == "targeted_applications" for block in strategy.schedule)


def test_rest_weekend_waives_only_weekend_kr_targets_and_does_not_carry_over():
    rest = strategy_for_week(date(2026, 8, 17))
    following = strategy_for_week(date(2026, 8, 24))
    assert rest.baseline_targets.linkedin_posts == 1
    assert rest.effective_targets.linkedin_posts == 0
    assert rest.effective_targets.stats_deep_minutes == 0
    assert rest.effective_targets.coffee_chats == 5
    assert following.effective_targets.linkedin_posts == 1
    assert following.effective_targets.stats_deep_minutes == 120
