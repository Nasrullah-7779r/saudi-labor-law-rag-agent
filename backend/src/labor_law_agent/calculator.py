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

Service length is measured in calendar years: whole years count anniversaries of the
start date (a 29 Feb start rolls to 28 Feb in non-leap years); the remaining days are a
fraction of the service year they fall in.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

ARTICLE_DISMISSAL_WITHOUT_AWARD = 80
ARTICLE_AWARD = 84
ARTICLE_RESIGNATION = 85
ARTICLE_FULL_AWARD_EXCEPTIONS = 87

HALF_RATE_BAND_YEARS = 5
RESIGNATION_MIN_YEARS = 2
RESIGNATION_TWO_THIRDS_YEARS = 5
RESIGNATION_FULL_YEARS = 10

CENTS = Decimal("0.01")
FRACTION_PRECISION = Decimal("0.0001")


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


def _to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _anniversary(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # 29 Feb start, non-leap target year
        return date(start.year + years, 2, 28)


def service_years(start: date, end: date) -> Decimal:
    """Calendar service length: whole anniversaries plus a pro-rata partial year."""
    whole = end.year - start.year
    if _anniversary(start, whole) > end:
        whole -= 1
    last = _anniversary(start, whole)
    next_ = _anniversary(start, whole + 1)
    partial = Decimal((end - last).days) / Decimal((next_ - last).days)
    return Decimal(whole) + partial


def _resignation_fraction(years: Decimal) -> Decimal:
    if years < RESIGNATION_MIN_YEARS:
        return Decimal(0)
    if years < RESIGNATION_TWO_THIRDS_YEARS:
        return Decimal(1) / Decimal(3)
    if years < RESIGNATION_FULL_YEARS:
        return Decimal(2) / Decimal(3)
    return Decimal(1)


def calculate_end_of_service(req: EndOfServiceRequest) -> EndOfServiceResult:
    years = service_years(req.start_date, req.end_date)
    wage = req.last_monthly_wage

    half_rate_years = min(years, Decimal(HALF_RATE_BAND_YEARS))
    full_rate_years = max(years - HALF_RATE_BAND_YEARS, Decimal(0))
    breakdown = [
        BreakdownLine(
            description="First five years: half a month's wage per year (Art. 84)",
            years=_to_cents(half_rate_years),
            months_of_wage_per_year=Decimal("0.5"),
            amount=_to_cents(half_rate_years * wage / 2),
        )
    ]
    if full_rate_years > 0:
        breakdown.append(
            BreakdownLine(
                description="Years after the fifth: one month's wage per year (Art. 84)",
                years=_to_cents(full_rate_years),
                months_of_wage_per_year=Decimal(1),
                amount=_to_cents(full_rate_years * wage),
            )
        )
    # Sum the rounded lines so the breakdown always adds up to the award shown.
    full_award = sum((line.amount for line in breakdown), Decimal(0))

    articles = [ARTICLE_AWARD]
    match req.reason:
        case TerminationReason.RESIGNATION:
            fraction = _resignation_fraction(years)
            articles.append(ARTICLE_RESIGNATION)
        case TerminationReason.ARTICLE_87_EXCEPTION:
            fraction = Decimal(1)
            articles.append(ARTICLE_FULL_AWARD_EXCEPTIONS)
        case TerminationReason.ARTICLE_80_DISMISSAL:
            fraction = Decimal(0)
            articles.append(ARTICLE_DISMISSAL_WITHOUT_AWARD)
        case _:
            fraction = Decimal(1)

    return EndOfServiceResult(
        service_years=_to_cents(years),
        full_award=full_award,
        entitlement_fraction=fraction.quantize(FRACTION_PRECISION, rounding=ROUND_HALF_UP),
        amount=_to_cents(full_award * fraction),
        breakdown=breakdown,
        applied_articles=sorted(articles),
    )
