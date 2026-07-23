from datetime import date, time

import pytest

from okr.calendar import (
    CAMPAIGN_END,
    CAMPAIGN_START,
    ScheduleBlock,
    ScheduleValidationError,
    campaign_week,
    schedule_for_week,
    validate_schedule,
)


def test_campaign_is_fifteen_monday_to_sunday_weeks():
    assert campaign_week(CAMPAIGN_START) == 1
    assert campaign_week(date(2026, 8, 10)) == 4
    assert campaign_week(date(2026, 9, 21)) == 10
    assert campaign_week(CAMPAIGN_END) == 15


def test_campaign_week_rejects_dates_outside_runway():
    with pytest.raises(ValueError):
        campaign_week(date(2026, 7, 19))


def test_normal_week_materializes_fixed_schedule_and_hours():
    blocks = schedule_for_week(date(2026, 7, 20))
    assert len([block for block in blocks if block.kind == "coffee_chat"]) == 5
    assert sum(block.minutes for block in blocks if block.kind == "commute_review") == 450
    assert sum(block.minutes for block in blocks if block.kind == "coding") == 180
    assert sum(block.minutes for block in blocks if block.kind == "targeted_applications") == 240
    review = next(block for block in blocks if block.kind == "weekly_review")
    assert (review.start, review.end) == (time(11), time(12))


def test_rest_weekend_suppresses_every_weekend_block_without_touching_weekdays():
    blocks = schedule_for_week(date(2026, 8, 17))
    assert all(block.day not in {date(2026, 8, 22), date(2026, 8, 23)} for block in blocks)
    assert len([block for block in blocks if block.kind == "coffee_chat"]) == 5
    waived = schedule_for_week(date(2026, 8, 17), include_rest=True)
    assert any(block.day == date(2026, 8, 22) for block in waived)


def test_commute_must_be_review_only():
    invalid = ScheduleBlock(
        date(2026, 7, 20), "coding", "Coding", 60, mode="commute"
    )
    with pytest.raises(ScheduleValidationError, match="review-only"):
        validate_schedule((invalid,))


def test_weekday_production_cannot_overlap_work_except_exact_lunch_window():
    invalid = ScheduleBlock(
        date(2026, 7, 20),
        "application",
        "Apply",
        60,
        time(17),
        time(18),
    )
    with pytest.raises(ScheduleValidationError, match="work hours"):
        validate_schedule((invalid,))
    lunch = ScheduleBlock(
        date(2026, 7, 20),
        "coffee_chat",
        "Chat",
        30,
        time(12, 15),
        time(12, 45),
        mode="lunch",
    )
    validate_schedule((lunch,))


def test_schedule_validation_rejects_overlaps_and_duration_mismatch():
    first = ScheduleBlock(
        date(2026, 7, 25), "one", "One", 60, time(10), time(11)
    )
    overlap = ScheduleBlock(
        date(2026, 7, 25), "two", "Two", 60, time(10, 30), time(11, 30)
    )
    with pytest.raises(ScheduleValidationError, match="overlaps"):
        validate_schedule((first, overlap))
    bad_duration = ScheduleBlock(
        date(2026, 7, 25), "bad", "Bad", 30, time(10), time(11)
    )
    with pytest.raises(ScheduleValidationError, match="declares"):
        validate_schedule((bad_duration,))
