"""Salary extraction and aggregation helpers for heterogeneous job-board payloads."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SalaryRange:
    """Represent salary range."""
    minimum: float | None = None
    maximum: float | None = None
    currency: str = ""
    period: str = ""

    @property
    def average(self) -> float | None:
        """Average."""
        if self.minimum is None or self.maximum is None:
            return None
        return (self.minimum + self.maximum) / 2


def _number(value: object) -> float | None:
    """Number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    number = float(match.group().replace(",", ""))
    suffix = value[match.end():].lstrip().casefold()
    if suffix.startswith("k"):
        number *= 1_000
    return number


def _text(value: object) -> str:
    """Text."""
    if isinstance(value, Mapping):
        return str(value.get("id") or value.get("name") or value.get("value") or "")
    return str(value or "")


def _period(value: object) -> str:
    """Period."""
    text = _text(value).strip().casefold()
    if "year" in text or "annual" in text:
        return "YEAR"
    if "month" in text:
        return "MONTH"
    if "week" in text:
        return "WEEK"
    if "day" in text:
        return "DAY"
    if "hour" in text:
        return "HOUR"
    return text.upper()


def extract_salary(payload: Mapping[str, object] | None) -> SalaryRange:
    """Extract common MCF, LinkedIn/Apify, and schema.org salary shapes."""
    if not payload:
        return SalaryRange()
    candidate: Mapping[str, object] = payload
    for key in ("baseSalary", "salaryInfo", "salary", "compensation"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            candidate = value
            break
    value = candidate.get("value")
    if isinstance(value, Mapping):
        candidate = {**candidate, **value}

    minimum = next((_number(candidate.get(k)) for k in
                    ("minimum", "minValue", "minSalary", "salaryMin", "min")
                    if _number(candidate.get(k)) is not None), None)
    maximum = next((_number(candidate.get(k)) for k in
                    ("maximum", "maxValue", "maxSalary", "salaryMax", "max")
                    if _number(candidate.get(k)) is not None), None)
    exact = _number(candidate.get("value"))
    if minimum is None and maximum is None and exact is not None:
        minimum = maximum = exact
    currency = _text(
        candidate.get("currency") or candidate.get("salaryCurrency")
        or payload.get("salaryCurrency") or payload.get("currency")
    ).strip().upper()
    period = _period(
        candidate.get("unitText") or candidate.get("period") or candidate.get("type")
        or candidate.get("payPeriod") or candidate.get("salaryPeriod")
    )
    if minimum is not None and maximum is not None and minimum > maximum:
        minimum, maximum = maximum, minimum
    return SalaryRange(minimum, maximum, currency, period)


def aggregate_salary(
    left: SalaryRange, right: SalaryRange
) -> SalaryRange:
    """Combine observations only when their declared currency/period are compatible."""
    if not any((right.minimum, right.maximum)):
        return left
    if not any((left.minimum, left.maximum)):
        return right
    if left.currency and right.currency and left.currency != right.currency:
        return left
    if left.period and right.period and left.period != right.period:
        return left
    mins = [v for v in (left.minimum, right.minimum) if v is not None]
    maxes = [v for v in (left.maximum, right.maximum) if v is not None]
    return SalaryRange(
        min(mins) if mins else None,
        max(maxes) if maxes else None,
        left.currency or right.currency,
        left.period or right.period,
    )


def is_below_monthly_sgd_floor(salary: SalaryRange, floor: float) -> bool:
    """Return whether a conclusive SGD salary maximum is below a monthly floor.

    Unknown currencies, periods, and open-ended ranges are retained so that an
    incomplete job-board payload cannot hide an otherwise suitable role.
    """
    if salary.currency.strip().upper() != "SGD" or salary.maximum is None:
        return False
    period = salary.period.strip().upper()
    if period == "MONTH":
        monthly_maximum = salary.maximum
    elif period == "YEAR":
        monthly_maximum = salary.maximum / 12
    else:
        return False
    return monthly_maximum < floor
