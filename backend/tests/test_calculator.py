from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from labor_law_agent.calculator import (
    EndOfServiceRequest,
    ServiceCalendar,
    calculate_end_of_service,
    service_years,
)
from labor_law_agent.calculator import (
    TerminationReason as R,
)

WAGE = Decimal(10000)
START = date(2010, 1, 1)


def _on(years: int, days: int = 0) -> date:
    """Calendar anniversary of START (N years later), offset by ``days``."""
    return date(START.year + years, START.month, START.day) + timedelta(days=days)


def _calc(end: date, reason: R, wage: Decimal = WAGE):
    return calculate_end_of_service(
        EndOfServiceRequest(
            last_monthly_wage=wage,
            start_date=START,
            end_date=end,
            reason=reason,
            calendar=ServiceCalendar.GREGORIAN,
        )
    )


# Expected values by hand (wage 10000):
#   years = whole anniversaries + leftover days / days in that service year
#   full = 0.5*wage*min(y,5) + wage*max(y-5,0), each line rounded half-up to cents
#   resignation fraction (Art. 85): 0 below 2y, 1/3 for 2 to 5 inclusive, 2/3 above 5 to <10, 1 from 10y
@pytest.mark.parametrize(
    ("end", "reason", "amount", "articles"),
    [
        (_on(0), R.EMPLOYER_TERMINATION, "0.00", [84]),  # same day
        (_on(1), R.EMPLOYER_TERMINATION, "5000.00", [84]),
        (_on(5), R.EMPLOYER_TERMINATION, "25000.00", [84]),
        (_on(7), R.CONTRACT_EXPIRY, "45000.00", [84]),
        # 2 + 73/366 (2012 is a leap year): 10000 + 5000*73/366 = 10997.2677... -> 10997.27
        (_on(2, 73), R.EMPLOYER_TERMINATION, "10997.27", [84]),
        (_on(2, -1), R.RESIGNATION, "0.00", [84, 85]),  # 1 + 364/365 = 1.997y, under 2
        (_on(2), R.RESIGNATION, "3333.33", [84, 85]),  # exactly 2 -> 1/3 of 10000
        (_on(5), R.RESIGNATION, "8333.33", [84, 85]),  # exactly 5 -> still 1/3 of 25000 (inclusive)
        (_on(10), R.RESIGNATION, "75000.00", [84, 85]),  # exactly 10 -> full
        (_on(3), R.ARTICLE_87_EXCEPTION, "15000.00", [84, 87]),
        (_on(3), R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
        # resignation band boundaries
        # 2 + 1/366: line 10013.66; 1/3 of 10013.66 = 3337.8866... -> 3337.89
        (_on(2, 1), R.RESIGNATION, "3337.89", [84, 85]),
        (_on(4), R.RESIGNATION, "6666.67", [84, 85]),  # 1/3 of 20000
        # 4 + 364/365 = 4.99726y: line 24986.30; 1/3 of it = 8328.7666... -> 8328.77
        (_on(5, -1), R.RESIGNATION, "8328.77", [84, 85]),
        # 5 + 1/365: lines 25000.00 + 27.40 = 25027.40; 2/3 of it = 16684.9333... -> 16684.93
        (_on(5, 1), R.RESIGNATION, "16684.93", [84, 85]),
        # 9 + 364/365 = 9.99726y: lines 25000.00 + 49972.60 = 74972.60; 2/3 = 49981.7333... -> 49981.73
        (_on(10, -1), R.RESIGNATION, "49981.73", [84, 85]),
        (_on(12), R.RESIGNATION, "95000.00", [84, 85]),  # beyond 10y: full 25000 + 7*10000
        # partial year beyond the fifth: 5 + 183/365 = 5.50137y -> 25000 + 10000*183/365
        (_on(5, 183), R.EMPLOYER_TERMINATION, "30013.70", [84]),
        (_on(5, 1), R.CONTRACT_EXPIRY, "25027.40", [84]),  # one day past 5y
        (_on(5, -1), R.EMPLOYER_TERMINATION, "24986.30", [84]),  # one day short of 5y
        # same-day, every reason
        (_on(0), R.RESIGNATION, "0.00", [84, 85]),
        (_on(0), R.ARTICLE_87_EXCEPTION, "0.00", [84, 87]),
        (_on(0), R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
        # Art. 87 pays in full even under 2 years of service
        (_on(0, 100), R.ARTICLE_87_EXCEPTION, "1369.86", [84, 87]),
        # Art. 80 pays nothing even after a long service
        (_on(12), R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
    ],
)
def test_award(end: date, reason: R, amount: str, articles: list[int]) -> None:
    result = _calc(end, reason)
    assert result.amount == Decimal(amount)
    assert result.applied_articles == articles


def test_breakdown_sums_to_full_award() -> None:
    result = _calc(_on(8), R.EMPLOYER_TERMINATION)
    assert len(result.breakdown) == 2
    assert sum(line.amount for line in result.breakdown) == result.full_award == Decimal(55000)


@pytest.mark.parametrize(
    ("wage", "start", "end"),
    [
        (Decimal(1000), date(2020, 1, 2), date(2020, 1, 1)),  # end before start
        (Decimal(0), START, date(2020, 1, 1)),
        (Decimal(-5), START, date(2020, 1, 1)),
    ],
)
def test_invalid_inputs(wage: Decimal, start: date, end: date) -> None:
    with pytest.raises(ValidationError):
        EndOfServiceRequest(
            last_monthly_wage=wage,
            start_date=start,
            end_date=end,
            reason=R.RESIGNATION,
            calendar=ServiceCalendar.GREGORIAN,
        )


def test_breakdown_single_line_up_to_five_years() -> None:
    for end in (_on(3), _on(5)):  # exactly 5y has no second band
        result = _calc(end, R.EMPLOYER_TERMINATION)
        assert len(result.breakdown) == 1
        assert result.breakdown[0].months_of_wage_per_year == Decimal("0.5")


def test_breakdown_two_lines_beyond_five_years() -> None:
    result = _calc(_on(5, 183), R.EMPLOYER_TERMINATION)
    first, rest = result.breakdown
    assert (first.years, first.months_of_wage_per_year, first.amount) == (
        Decimal("5.00"),
        Decimal("0.5"),
        Decimal("25000.00"),
    )
    assert (rest.years, rest.months_of_wage_per_year, rest.amount) == (
        Decimal("0.50"),
        Decimal(1),
        Decimal("5013.70"),
    )
    assert result.service_years == Decimal("5.50")
    assert result.full_award == Decimal("30013.70")


@pytest.mark.parametrize(
    ("end", "reason", "full_award", "fraction"),
    [
        (_on(4), R.EMPLOYER_TERMINATION, "20000.00", "1.0000"),
        (_on(4), R.RESIGNATION, "20000.00", "0.3333"),
        (_on(7), R.RESIGNATION, "45000.00", "0.6667"),
        (_on(10), R.RESIGNATION, "75000.00", "1.0000"),
        (_on(1), R.RESIGNATION, "5000.00", "0.0000"),
        (_on(2), R.RESIGNATION, "10000.00", "0.3333"),  # exactly 2y -> 1/3
        (_on(5), R.RESIGNATION, "25000.00", "0.3333"),  # exactly 5y -> 1/3 (inclusive)
        (_on(5, 1), R.RESIGNATION, "25027.40", "0.6667"),  # 5y + 1 day -> 2/3
        (_on(10, -1), R.RESIGNATION, "74972.60", "0.6667"),  # just under 10y -> 2/3
        (_on(12), R.ARTICLE_81_WORKER_LEAVES, "95000.00", "1.0000"),
        (_on(12), R.ARTICLE_80_DISMISSAL, "95000.00", "0.0000"),  # full award still reported
        (_on(1), R.ARTICLE_87_EXCEPTION, "5000.00", "1.0000"),
    ],
)
def test_full_award_and_fraction_reported(
    end: date, reason: R, full_award: str, fraction: str
) -> None:
    result = _calc(end, reason)
    assert result.full_award == Decimal(full_award)
    assert result.entitlement_fraction == Decimal(fraction)


def test_same_day_resignation_is_zero() -> None:
    result = _calc(_on(0), R.RESIGNATION)
    assert result.service_years == Decimal("0.00")
    assert result.full_award == Decimal("0.00")
    assert result.amount == Decimal("0.00")
    assert result.entitlement_fraction == Decimal("0.0000")
    assert len(result.breakdown) == 1


def test_amounts_round_half_up_not_bankers() -> None:
    # 1 year * 0.01 / 2 = 0.005 exactly -> half-up gives 0.01 (banker's would give 0.00)
    result = _calc(_on(1), R.EMPLOYER_TERMINATION, wage=Decimal("0.01"))
    assert result.amount == Decimal("0.01")
    assert result.full_award == Decimal("0.01")


def test_end_date_equal_to_start_date_is_valid() -> None:
    req = EndOfServiceRequest(
        last_monthly_wage=WAGE,
        start_date=START,
        end_date=START,
        reason=R.RESIGNATION,
        calendar=ServiceCalendar.GREGORIAN,
    )
    assert calculate_end_of_service(req).amount == Decimal("0.00")


def _calc_between(start: date, end: date, reason: R, wage: Decimal = WAGE):
    return calculate_end_of_service(
        EndOfServiceRequest(
            last_monthly_wage=wage,
            start_date=start,
            end_date=end,
            reason=reason,
            calendar=ServiceCalendar.GREGORIAN,
        )
    )


@pytest.mark.parametrize(
    ("start", "end", "fraction"),
    [
        # one day short of 5 calendar years (1826 days; days/365 would say 5.002y -> 2/3)
        (date(2012, 1, 1), date(2016, 12, 31), "0.3333"),
        # one day short of 2 years across the 2012 leap day (730 days; days/365 = 2.0 -> 1/3)
        (date(2011, 3, 1), date(2013, 2, 28), "0.0000"),
        # one day short of 10 years across three leap days (3652 days; days/365 > 10 -> full)
        (date(2012, 1, 1), date(2021, 12, 31), "0.6667"),
        # exactly on the anniversaries, across leap days: 5y is still 1/3 (upper bound inclusive)
        (date(2012, 1, 1), date(2017, 1, 1), "0.3333"),
        (date(2012, 1, 1), date(2017, 1, 2), "0.6667"),
        (date(2011, 3, 1), date(2013, 3, 1), "0.3333"),
        (date(2012, 1, 1), date(2022, 1, 1), "1.0000"),
    ],
)
def test_resignation_band_uses_calendar_years_across_leap_days(
    start: date, end: date, fraction: str
) -> None:
    result = _calc_between(start, end, R.RESIGNATION)
    assert result.entitlement_fraction == Decimal(fraction)


@pytest.mark.parametrize(
    ("start", "end", "years"),
    [
        (date(2010, 1, 1), date(2010, 1, 1), 0),
        (date(2010, 6, 15), date(2011, 6, 15), 1),
        (date(2012, 1, 1), date(2017, 1, 1), 5),
        (date(2011, 3, 1), date(2021, 3, 1), 10),
        (date(2012, 2, 29), date(2013, 2, 28), 1),  # 29 Feb start rolls to 28 Feb
        (date(2012, 2, 29), date(2016, 2, 29), 4),
    ],
)
def test_service_years_exact_on_anniversary(start: date, end: date, years: int) -> None:
    assert service_years(start, end, ServiceCalendar.GREGORIAN) == Decimal(years)


def test_service_years_one_day_before_anniversary_is_below_whole_year() -> None:
    assert service_years(date(2012, 2, 29), date(2013, 2, 27), ServiceCalendar.GREGORIAN) < 1
    assert service_years(date(2012, 1, 1), date(2016, 12, 31), ServiceCalendar.GREGORIAN) < 5


def test_partial_year_uses_length_of_its_own_service_year() -> None:
    # service year 2011-03-01..2012-03-01 has 366 days (contains 29 Feb 2012)
    assert service_years(
        date(2011, 3, 1), date(2011, 3, 1) + timedelta(days=183), ServiceCalendar.GREGORIAN
    ) == Decimal(183) / Decimal(366)
    # service year 2012-03-01..2013-03-01 has 365 days
    assert service_years(
        date(2012, 3, 1), date(2012, 3, 1) + timedelta(days=183), ServiceCalendar.GREGORIAN
    ) == Decimal(183) / Decimal(365)
    # whole years plus a partial in a 366-day service year
    assert service_years(
        date(2011, 3, 1), date(2012, 3, 1) + timedelta(days=61), ServiceCalendar.GREGORIAN
    ) == 1 + Decimal(61) / Decimal(365)


@pytest.mark.parametrize(
    ("wage", "start", "end"),
    [
        ("3333.33", date(2010, 1, 1), date(2018, 5, 20)),
        ("3333.33", date(2012, 1, 1), date(2016, 12, 31)),
        ("7777.77", date(2011, 3, 1), date(2024, 11, 9)),
        ("1234.57", date(2012, 2, 29), date(2019, 8, 31)),
        ("9999.99", date(2010, 1, 1), date(2010, 7, 4)),
        ("0.03", date(2010, 1, 1), date(2017, 4, 2)),
        ("100000.01", date(2000, 5, 17), date(2025, 12, 30)),
    ],
)
@pytest.mark.parametrize("reason", [R.EMPLOYER_TERMINATION, R.RESIGNATION])
def test_breakdown_lines_add_up_to_full_award_exactly(
    wage: str, start: date, end: date, reason: R
) -> None:
    result = _calc_between(start, end, reason, wage=Decimal(wage))
    assert sum(line.amount for line in result.breakdown) == result.full_award


@pytest.mark.parametrize(("years", "amount"), [(1, "5000.00"), (12, "95000.00")])
def test_article_81_worker_leaves_gets_full_award(years: int, amount: str) -> None:
    result = _calc(_on(years), R.ARTICLE_81_WORKER_LEAVES)
    assert result.amount == result.full_award == Decimal(amount)
    assert result.entitlement_fraction == Decimal("1.0000")
    assert result.applied_articles == [81, 84]
