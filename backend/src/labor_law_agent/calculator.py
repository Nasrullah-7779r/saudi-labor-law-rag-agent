"""End-of-service award calculator (Saudi Labor Law, Articles 84, 85, 87).

Pure function, no I/O.

Rules encoded (TO VERIFY against the current BOE Arabic consolidation before release):
- Art. 84: half a month's wage for each of the first five years of service and one
  month's wage for each year after that; partial years count pro rata. The award is
  computed on the last wage.
- Art. 85: on resignation, one third of the award for 2 to <5 years of service, two
  thirds for 5 to <10 years, the full award for 10 years or more; nothing below 2 years.
- Art. 87: full award despite leaving at the worker's own initiative in the cases the
  article lists (force majeure, a female worker within the set period after marriage or
  childbirth, or leaving under Art. 81).
- Art. 80: no award when the employer terminates under Article 80.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

DAYS_PER_YEAR = Decimal(365)
FIRST_BAND_YEARS = Decimal(5)
CENTS = Decimal("0.01")


class TerminationReason(StrEnum):
    EMPLOYER_TERMINATION = "employer_termination"
    CONTRACT_EXPIRY = "contract_expiry"
    RESIGNATION = "resignation"
    ARTICLE_87_EXCEPTION = "article_87_exception"
    ARTICLE_80_DISMISSAL = "article_80_dismissal"


class EndOfServiceRequest(BaseModel):
    last_monthly_wage: Decimal = Field(gt=0)
    start_date: date
    end_date: date
    reason: TerminationReason

    @model_validator(mode="after")
    def _end_after_start(self) -> EndOfServiceRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class BreakdownLine(BaseModel):
    description: str
    years: Decimal
    months_of_wage_per_year: Decimal
    amount: Decimal


class EndOfServiceResult(BaseModel):
    service_years: Decimal
    full_award: Decimal
    entitlement_fraction: Decimal
    amount: Decimal
    breakdown: list[BreakdownLine]
    applied_articles: list[int]


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _resignation_fraction(years: Decimal) -> Decimal:
    if years < 2:
        return Decimal(0)
    if years < 5:
        return Decimal(1) / Decimal(3)
    if years < 10:
        return Decimal(2) / Decimal(3)
    return Decimal(1)


def calculate_end_of_service(req: EndOfServiceRequest) -> EndOfServiceResult:
    days = Decimal((req.end_date - req.start_date).days)
    years = days / DAYS_PER_YEAR
    wage = req.last_monthly_wage

    first = min(years, FIRST_BAND_YEARS)
    rest = max(years - FIRST_BAND_YEARS, Decimal(0))
    breakdown = [
        BreakdownLine(
            description="First five years: half a month's wage per year (Art. 84)",
            years=_q(first),
            months_of_wage_per_year=Decimal("0.5"),
            amount=_q(first * wage / 2),
        )
    ]
    if rest > 0:
        breakdown.append(
            BreakdownLine(
                description="Years after the fifth: one month's wage per year (Art. 84)",
                years=_q(rest),
                months_of_wage_per_year=Decimal(1),
                amount=_q(rest * wage),
            )
        )
    full_award = first * wage / 2 + rest * wage

    articles = [84]
    match req.reason:
        case TerminationReason.RESIGNATION:
            fraction = _resignation_fraction(years)
            articles.append(85)
        case TerminationReason.ARTICLE_87_EXCEPTION:
            fraction = Decimal(1)
            articles.append(87)
        case TerminationReason.ARTICLE_80_DISMISSAL:
            fraction = Decimal(0)
            articles.append(80)
        case _:
            fraction = Decimal(1)

    return EndOfServiceResult(
        service_years=_q(years),
        full_award=_q(full_award),
        entitlement_fraction=fraction.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        amount=_q(full_award * fraction),
        breakdown=breakdown,
        applied_articles=sorted(articles),
    )
