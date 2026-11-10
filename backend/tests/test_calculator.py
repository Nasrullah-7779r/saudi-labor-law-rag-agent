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
