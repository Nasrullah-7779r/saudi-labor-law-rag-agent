from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from labor_law_agent.calculator import (
    EndOfServiceRequest,
    calculate_end_of_service,
)
from labor_law_agent.calculator import (
    TerminationReason as R,
)

WAGE = Decimal(10000)
START = date(2010, 1, 1)


def _calc(days: int, reason: R, wage: Decimal = WAGE):
    end = date.fromordinal(START.toordinal() + days)
    return calculate_end_of_service(
        EndOfServiceRequest(last_monthly_wage=wage, start_date=START, end_date=end, reason=reason)
    )


# Expected values by hand: years = days / 365; full = 0.5*wage*min(y,5) + wage*max(y-5,0)
@pytest.mark.parametrize(
    ("days", "reason", "amount", "articles"),
    [
        (0, R.EMPLOYER_TERMINATION, "0.00", [84]),  # same day
        (365, R.EMPLOYER_TERMINATION, "5000.00", [84]),
        (365 * 5, R.EMPLOYER_TERMINATION, "25000.00", [84]),
        (365 * 7, R.CONTRACT_EXPIRY, "45000.00", [84]),
        (365 * 2 + 73, R.EMPLOYER_TERMINATION, "11000.00", [84]),  # 2.2 years
        (365 * 2 - 1, R.RESIGNATION, "0.00", [84, 85]),  # just under 2
        (365 * 2, R.RESIGNATION, "3333.33", [84, 85]),  # exactly 2 -> 1/3 of 10000
        (365 * 5, R.RESIGNATION, "16666.67", [84, 85]),  # exactly 5 -> 2/3 of 25000
        (365 * 10, R.RESIGNATION, "75000.00", [84, 85]),  # exactly 10 -> full
        (365 * 3, R.ARTICLE_87_EXCEPTION, "15000.00", [84, 87]),
        (365 * 3, R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
        # resignation band boundaries
        (365 * 2 + 1, R.RESIGNATION, "3337.90", [84, 85]),  # just over 2y: 1/3 of 10013.69863
        (365 * 4, R.RESIGNATION, "6666.67", [84, 85]),  # 1/3 of 20000
        (365 * 5 - 1, R.RESIGNATION, "8328.77", [84, 85]),  # just under 5y: 1/3 of 24986.30137
        (365 * 5 + 1, R.RESIGNATION, "16684.93", [84, 85]),  # just over 5y: 2/3 of 25027.39726
        (365 * 10 - 1, R.RESIGNATION, "49981.74", [84, 85]),  # just under 10y: 2/3 of 74972.60274
        (365 * 12, R.RESIGNATION, "95000.00", [84, 85]),  # beyond 10y: full 25000 + 7*10000
        # partial year beyond the fifth: 5y + 183d = 5.50137y -> 25000 + 10000*183/365
        (365 * 5 + 183, R.EMPLOYER_TERMINATION, "30013.70", [84]),
        (365 * 5 + 1, R.CONTRACT_EXPIRY, "25027.40", [84]),  # one day past 5y
        (365 * 5 - 1, R.EMPLOYER_TERMINATION, "24986.30", [84]),  # one day short of 5y
        # same-day, every reason
        (0, R.RESIGNATION, "0.00", [84, 85]),
        (0, R.ARTICLE_87_EXCEPTION, "0.00", [84, 87]),
        (0, R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
        # Art. 87 pays in full even under 2 years of service
        (100, R.ARTICLE_87_EXCEPTION, "1369.86", [84, 87]),
        # Art. 80 pays nothing even after a long service
        (365 * 12, R.ARTICLE_80_DISMISSAL, "0.00", [80, 84]),
    ],
)
def test_award(days: int, reason: R, amount: str, articles: list[int]) -> None:
    result = _calc(days, reason)
    assert result.amount == Decimal(amount)
    assert result.applied_articles == articles


def test_breakdown_sums_to_full_award() -> None:
    result = _calc(365 * 8, R.EMPLOYER_TERMINATION)
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
            last_monthly_wage=wage, start_date=start, end_date=end, reason=R.RESIGNATION
        )


def test_breakdown_single_line_up_to_five_years() -> None:
    for days in (365 * 3, 365 * 5):  # exactly 5y has no second band
        result = _calc(days, R.EMPLOYER_TERMINATION)
        assert len(result.breakdown) == 1
        assert result.breakdown[0].months_of_wage_per_year == Decimal("0.5")


def test_breakdown_two_lines_beyond_five_years() -> None:
    result = _calc(365 * 5 + 183, R.EMPLOYER_TERMINATION)
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
    ("days", "reason", "full_award", "fraction"),
    [
        (365 * 4, R.EMPLOYER_TERMINATION, "20000.00", "1.0000"),
        (365 * 4, R.RESIGNATION, "20000.00", "0.3333"),
        (365 * 7, R.RESIGNATION, "45000.00", "0.6667"),
        (365 * 10, R.RESIGNATION, "75000.00", "1.0000"),
        (365 * 1, R.RESIGNATION, "5000.00", "0.0000"),
        (365 * 12, R.ARTICLE_80_DISMISSAL, "95000.00", "0.0000"),  # full award still reported
        (365 * 1, R.ARTICLE_87_EXCEPTION, "5000.00", "1.0000"),
    ],
)
def test_full_award_and_fraction_reported(
    days: int, reason: R, full_award: str, fraction: str
) -> None:
    result = _calc(days, reason)
    assert result.full_award == Decimal(full_award)
    assert result.entitlement_fraction == Decimal(fraction)


def test_same_day_resignation_is_zero() -> None:
    result = _calc(0, R.RESIGNATION)
    assert result.service_years == Decimal("0.00")
    assert result.full_award == Decimal("0.00")
    assert result.amount == Decimal("0.00")
    assert result.entitlement_fraction == Decimal("0.0000")
    assert len(result.breakdown) == 1


def test_amounts_round_half_up_not_bankers() -> None:
    # 1 year * 0.01 / 2 = 0.005 exactly -> half-up gives 0.01 (banker's would give 0.00)
    result = _calc(365, R.EMPLOYER_TERMINATION, wage=Decimal("0.01"))
    assert result.amount == Decimal("0.01")
    assert result.full_award == Decimal("0.01")


def test_end_date_equal_to_start_date_is_valid() -> None:
    req = EndOfServiceRequest(
        last_monthly_wage=WAGE, start_date=START, end_date=START, reason=R.RESIGNATION
    )
    assert calculate_end_of_service(req).amount == Decimal("0.00")
