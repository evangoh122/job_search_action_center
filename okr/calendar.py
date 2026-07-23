"""Deterministic calendar rules for the job-search OKR.

This module deliberately has no database, network, or wall-clock dependencies.  Callers
provide dates, which keeps CLI output and tests reproducible in Asia/Singapore and elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, time, timedelta
from typing import Iterable

CAMPAIGN_START = date(2026, 7, 20)
CAMPAIGN_END = date(2026, 11, 1)
CAMPAIGN_TIMEZONE = "Asia/Singapore"

REST_DATES = frozenset(
    {
        date(2026, 8, 22),
        date(2026, 8, 23),
        date(2026, 9, 26),
        date(2026, 9, 27),
    }
)


class ScheduleValidationError(ValueError):
    """Raised when a block violates a campaign scheduling constraint."""


@dataclass(frozen=True, slots=True)
class ScheduleBlock:
    """One planned activity on a concrete campaign date.

    Commute review has no exact clock time because the supplied plan specifies only its
    daily duration. All other blocks retain their supplied clock times.
    """

    day: date
    kind: str
    label: str
    minutes: int
    start: time | None = None
    end: time | None = None
    mode: str = "production"
    review_only: bool = False


@dataclass(frozen=True, slots=True)
class _RecurringBlock:
    weekdays: tuple[int, ...]
    kind: str
    label: str
    minutes: int
    start: time | None = None
    end: time | None = None
    mode: str = "production"
    review_only: bool = False


_FIXED_BLOCKS = (
    _RecurringBlock(
        (0, 1, 2, 3, 4),
        "commute_review",
        "Review RAG notes, flashcards, and concepts",
        90,
        mode="commute",
        review_only=True,
    ),
    _RecurringBlock(
        (0, 1, 2, 3, 4),
        "coffee_chat",
        "Coffee chat / informational interview",
        30,
        time(12, 15),
        time(12, 45),
        mode="lunch",
    ),
    _RecurringBlock(
        (0, 2),
        "coding",
        "Coding challenges (hands-on)",
        90,
        time(19, 30),
        time(21, 0),
    ),
    _RecurringBlock(
        (1, 3),
        "targeted_applications",
        "Assemble and submit 5 targeted applications",
        120,
        time(19, 30),
        time(21, 30),
    ),
    _RecurringBlock(
        (5,),
        "stats_deep",
        "Stats/DS deep work",
        120,
        time(10, 0),
        time(12, 0),
    ),
    _RecurringBlock(
        (5,),
        "mock_and_sourcing",
        "Mock interviews and source next week's coffee chats",
        225,
        time(14, 0),
        time(17, 45),
    ),
    _RecurringBlock(
        (6,),
        "portfolio",
        "Portfolio/project work",
        180,
        time(8, 0),
        time(11, 0),
    ),
    _RecurringBlock(
        (6,),
        "weekly_review",
        "Weekly OKR review",
        60,
        time(11, 0),
        time(12, 0),
        mode="review",
        review_only=True,
    ),
    _RecurringBlock(
        (6,),
        "linkedin_post",
        "Publish LinkedIn post",
        30,
        time(17, 0),
        time(17, 30),
    ),
)


def monday_of(day: date) -> date:
    """Return the Monday containing ``day``."""
    return day - timedelta(days=day.weekday())


def campaign_week(day: date) -> int:
    """Return the one-based campaign week containing ``day``.

    The campaign is exactly fifteen Monday-to-Sunday weeks. Explicit milestone dates are
    therefore intentionally independent of the informal week labels in the source plan.
    """
    if not CAMPAIGN_START <= day <= CAMPAIGN_END:
        raise ValueError(f"{day.isoformat()} is outside the job-search campaign")
    return ((day - CAMPAIGN_START).days // 7) + 1


def schedule_for_week(day: date, *, include_rest: bool = False) -> tuple[ScheduleBlock, ...]:
    """Materialize the fixed schedule for the campaign week containing ``day``.

    Planned rest dates are omitted by default. ``include_rest`` is useful for displaying
    which blocks were deliberately waived, without changing the canonical rules.
    """
    week_start = monday_of(day)
    if week_start < CAMPAIGN_START or week_start > CAMPAIGN_END:
        raise ValueError(f"week of {week_start.isoformat()} is outside the campaign")
    blocks: list[ScheduleBlock] = []
    for offset in range(7):
        concrete_day = week_start + timedelta(days=offset)
        if concrete_day > CAMPAIGN_END:
            continue
        if concrete_day in REST_DATES and not include_rest:
            continue
        for spec in _FIXED_BLOCKS:
            if concrete_day.weekday() in spec.weekdays:
                blocks.append(
                    ScheduleBlock(
                        day=concrete_day,
                        kind=spec.kind,
                        label=spec.label,
                        minutes=spec.minutes,
                        start=spec.start,
                        end=spec.end,
                        mode=spec.mode,
                        review_only=spec.review_only,
                    )
                )
    validate_schedule(blocks)
    return tuple(blocks)


def replace_block(block: ScheduleBlock, **changes: object) -> ScheduleBlock:
    """Return a validated copy of a schedule block for a strategy pivot."""
    updated = replace(block, **changes)
    validate_schedule((updated,))
    return updated


def validate_schedule(blocks: Iterable[ScheduleBlock]) -> None:
    """Validate work-hour, commute, duration, and overlap constraints."""
    materialized = tuple(blocks)
    for block in materialized:
        if block.minutes <= 0:
            raise ScheduleValidationError("schedule block duration must be positive")
        if (block.start is None) != (block.end is None):
            raise ScheduleValidationError("start and end must either both be set or both be absent")
        if block.start is not None:
            actual = (
                block.end.hour * 60
                + block.end.minute
                - block.start.hour * 60
                - block.start.minute
            )
            if actual != block.minutes:
                raise ScheduleValidationError(
                    f"{block.kind} declares {block.minutes} minutes but spans {actual}"
                )
        if block.mode == "commute" and not block.review_only:
            raise ScheduleValidationError("commute blocks must be review-only")
        if block.mode == "commute" and block.kind != "commute_review":
            raise ScheduleValidationError("commute may contain review only, never production")
        if block.day.weekday() < 5 and block.start is not None:
            overlaps_work = block.start < time(18, 0) and block.end > time(9, 0)
            inside_lunch = block.start >= time(12, 15) and block.end <= time(12, 45)
            if overlaps_work and not inside_lunch:
                raise ScheduleValidationError(
                    f"{block.kind} overlaps weekday work hours outside the lunch slot"
                )

    timed = sorted(
        (block for block in materialized if block.start is not None),
        key=lambda block: (block.day, block.start),
    )
    for previous, current in zip(timed, timed[1:]):
        if previous.day == current.day and current.start < previous.end:
            raise ScheduleValidationError(
                f"{previous.kind} overlaps {current.kind} on {current.day.isoformat()}"
            )
