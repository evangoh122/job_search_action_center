"""Date-authoritative milestone pivots and effective weekly targets."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from okr.calendar import REST_DATES, ScheduleBlock, monday_of, replace_block, schedule_for_week

FIRST_INTERVIEW_CHECKPOINT = date(2026, 8, 10)
ONSITE_SHIFT = date(2026, 8, 31)
REFERRAL_PIVOT = date(2026, 9, 21)
PIPELINE_ONLY = date(2026, 10, 12)


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Observed outcomes that make conditional milestone pivots decidable."""

    interviews_landed: int = 0
    offers_in_play: int = 0


@dataclass(frozen=True, slots=True)
class WeeklyTargets:
    """Targets derived from the campaign rules for one week."""

    coffee_chats: int = 5
    targeted_applications: int = 10
    linkedin_posts: int = 1
    coding_minutes: int = 180
    stats_deep_minutes: int = 120
    commute_review_minutes: int = 450


@dataclass(frozen=True, slots=True)
class WeeklyStrategy:
    """Effective targets, schedule, and milestone guidance for a campaign week."""

    week_start: date
    baseline_targets: WeeklyTargets
    effective_targets: WeeklyTargets
    schedule: tuple[ScheduleBlock, ...]
    pivots: tuple[str, ...]


def strategy_for_week(day: date, context: StrategyContext | None = None) -> WeeklyStrategy:
    """Compute the strategy in force for the campaign week containing ``day``.

    Pivots use their explicit dates, not the inconsistent informal week numbers in the
    planning brief. Rest waives weekend output and never transfers it into another week.
    """
    context = context or StrategyContext()
    week_start = monday_of(day)
    baseline = WeeklyTargets()
    effective = baseline
    pivots: list[str] = []
    schedule = list(schedule_for_week(day))

    if week_start >= FIRST_INTERVIEW_CHECKPOINT and context.interviews_landed == 0:
        pivots.append("diagnose_targeting_or_resume")

    if week_start >= ONSITE_SHIFT:
        pivots.append("saturday_pm_mock_interviews_only")
        schedule = [
            replace_block(
                block,
                kind="mock_interview",
                label="Mock interviews",
            )
            if block.kind == "mock_and_sourcing"
            else block
            for block in schedule
        ]

    if week_start >= REFERRAL_PIVOT and context.offers_in_play == 0:
        pivots.append("reduce_applications_and_prioritize_referrals")
        effective = replace(effective, targeted_applications=5)
        thursday_changed = False
        redirected: list[ScheduleBlock] = []
        for block in schedule:
            if block.kind == "targeted_applications" and block.day.weekday() == 3:
                redirected.append(
                    replace_block(block, kind="referrals", label="Referral outreach")
                )
                thursday_changed = True
            else:
                redirected.append(block)
        schedule = redirected
        if not thursday_changed:
            # The final campaign week is still handled correctly if it is truncated.
            pivots.append("referral_block_unavailable")

    if week_start >= PIPELINE_ONLY:
        pivots.append("pipeline_closing_only")
        effective = replace(effective, targeted_applications=0)
        schedule = [
            replace_block(block, kind="pipeline_closing", label="Close active pipeline")
            if block.kind in {"targeted_applications", "referrals"}
            else block
            for block in schedule
        ]

    rest_days = REST_DATES.intersection(
        {week_start.fromordinal(week_start.toordinal() + offset) for offset in range(7)}
    )
    if rest_days:
        pivots.append("planned_rest_weekend")
        effective = replace(effective, linkedin_posts=0, stats_deep_minutes=0)

    return WeeklyStrategy(
        week_start=week_start,
        baseline_targets=baseline,
        effective_targets=effective,
        schedule=tuple(schedule),
        pivots=tuple(pivots),
    )
