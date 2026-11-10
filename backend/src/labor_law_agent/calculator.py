"""End-of-service award calculator (Saudi Labor Law, Articles 84, 85, 87).

Pure function, no I/O.

Rules encoded, checked against the BOE consolidated Arabic text (laws.boe.gov.sa, Labor Law
M/51 1426H as amended through 1446H; printed 1448/05/30H; Articles 81, 84, 85, 87 show no
amendment, Art. 80 is amended and was read in its current wording):
- Art. 84: half a month's wage for each of the first five years of service and one
  month's wage for each later year; parts of a year count pro rata; the last wage is
  the basis.
- Art. 85 (resignation): one third of the award for service of at least two and at most
  five consecutive years ("لا تقل ... عن سنتين ... ولا تزيد على خمس سنوات"), two thirds when
  it exceeds five years but is under ten, the full award at ten years or more; nothing
  under two years.
- Art. 87: full award despite Art. 85 when the worker leaves due to force majeure, or a
  female worker ends the contract within six months of her marriage contract or three
  months of giving birth.
- Art. 81: a worker who leaves in the cases it lists keeps all statutory rights (full award).
- Art. 80: no award when the employer terminates under Article 80.

Art. 10: all periods in the law are counted in the Hijri calendar unless the employment
contract or work regulations say otherwise, so ``ServiceCalendar.HIJRI`` is the default and
``GREGORIAN`` is for contracts that specify it. Dates are given as Gregorian dates either
way. Service length counts whole anniversaries of the start date in the chosen calendar
(a day that doesn't exist in the anniversary month, e.g. 29 Feb or Hijri day 30, rolls back
to the month's last day); the remaining days are a fraction of the service year they fall in.

Hijri conversion uses the Umm al-Qura calendar via ``hijridate`` 2.6
(https://pypi.org/project/hijridate/2.6.0/: ``Gregorian.fromdate(d).to_hijri()``,
``Hijri.month_length()``, ``Hijri.to_gregorian()``; supported range 1343-1500 AH,
1924-08-01 to 2077-11-16 CE).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from hijridate import Gregorian, Hijri
from pydantic import BaseModel, Field, model_validator

ARTICLE_DISMISSAL_WITHOUT_AWARD = 80
ARTICLE_WORKER_LEAVES_WITH_RIGHTS = 81
ARTICLE_AWARD = 84
ARTICLE_RESIGNATION = 85
ARTICLE_FULL_AWARD_EXCEPTIONS = 87

HALF_RATE_BAND_YEARS = 5
RESIGNATION_MIN_YEARS = 2
RESIGNATION_ONE_THIRD_MAX_YEARS = 5  # inclusive: exactly five years still gets one third
RESIGNATION_FULL_YEARS = 10

CENTS = Decimal("0.01")
FRACTION_PRECISION = Decimal("0.0001")

UMM_AL_QURA_FIRST_DATE = date(1924, 8, 1)
UMM_AL_QURA_LAST_DATE = date(2077, 11, 16)


class ServiceCalendar(StrEnum):
    HIJRI = "hijri"
    GREGORIAN = "gregorian"


class TerminationReason(StrEnum):
    EMPLOYER_TERMINATION = "employer_termination"
    CONTRACT_EXPIRY = "contract_expiry"
    RESIGNATION = "resignation"
    ARTICLE_81_WORKER_LEAVES = "article_81_worker_leaves"
    ARTICLE_87_EXCEPTION = "article_87_exception"
    ARTICLE_80_DISMISSAL = "article_80_dismissal"


class EndOfServiceRequest(BaseModel):
    last_monthly_wage: Decimal = Field(gt=0)
    start_date: date
    end_date: date
    reason: TerminationReason
    calendar: ServiceCalendar = ServiceCalendar.HIJRI

    @model_validator(mode="after")
    def _valid_dates(self) -> EndOfServiceRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.calendar is ServiceCalendar.HIJRI and not (
            UMM_AL_QURA_FIRST_DATE <= self.start_date
            and self.end_date <= UMM_AL_QURA_LAST_DATE
        ):
            raise ValueError(
                f"Hijri calculation supports dates from {UMM_AL_QURA_FIRST_DATE} "
                f"to {UMM_AL_QURA_LAST_DATE}"
            )
        return self


class BreakdownLine(BaseModel):
    description: str
    years: Decimal
    months_of_wage_per_year: Decimal
    amount: Decimal


class EndOfServiceResult(BaseModel):
    calendar: ServiceCalendar
    service_years: Decimal
    full_award: Decimal
    entitlement_fraction: Decimal
    amount: Decimal
    breakdown: list[BreakdownLine]
    applied_articles: list[int]


def _to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _gregorian_anniversary(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # 29 Feb start, non-leap target year
        return date(start.year + years, 2, 28)


def _hijri_anniversary(start: date, years: int) -> date:
    h = Gregorian.fromdate(start).to_hijri()
    month_start = Hijri(h.year + years, h.month, 1)
    day = min(h.day, month_start.month_length())
    g = Hijri(h.year + years, h.month, day).to_gregorian()
    return date(g.year, g.month, g.day)


def _hijri_year_gap(start: date, end: date) -> int:
    return Gregorian.fromdate(end).to_hijri().year - Gregorian.fromdate(start).to_hijri().year


def service_years(
    start: date, end: date, calendar: ServiceCalendar = ServiceCalendar.HIJRI
) -> Decimal:
    """Service length in the chosen calendar: whole anniversaries plus a pro-rata part."""
    if calendar is ServiceCalendar.HIJRI:
        anniversary = _hijri_anniversary
        whole = _hijri_year_gap(start, end)
    else:
        anniversary = _gregorian_anniversary
        whole = end.year - start.year
    if anniversary(start, whole) > end:
        whole -= 1
    last = anniversary(start, whole)
    next_ = anniversary(start, whole + 1)
    partial = Decimal((end - last).days) / Decimal((next_ - last).days)
    return Decimal(whole) + partial


def _resignation_fraction(years: Decimal) -> Decimal:
    if years < RESIGNATION_MIN_YEARS:
        return Decimal(0)
    if years <= RESIGNATION_ONE_THIRD_MAX_YEARS:
        return Decimal(1) / Decimal(3)
    if years < RESIGNATION_FULL_YEARS:
        return Decimal(2) / Decimal(3)
    return Decimal(1)


def calculate_end_of_service(req: EndOfServiceRequest) -> EndOfServiceResult:
    years = service_years(req.start_date, req.end_date, req.calendar)
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
        case TerminationReason.ARTICLE_81_WORKER_LEAVES:
            fraction = Decimal(1)
            articles.append(ARTICLE_WORKER_LEAVES_WITH_RIGHTS)
        case TerminationReason.ARTICLE_87_EXCEPTION:
            fraction = Decimal(1)
            articles.append(ARTICLE_FULL_AWARD_EXCEPTIONS)
        case TerminationReason.ARTICLE_80_DISMISSAL:
            fraction = Decimal(0)
            articles.append(ARTICLE_DISMISSAL_WITHOUT_AWARD)
        case _:
            fraction = Decimal(1)

    return EndOfServiceResult(
        calendar=req.calendar,
        service_years=_to_cents(years),
        full_award=full_award,
        entitlement_fraction=fraction.quantize(FRACTION_PRECISION, rounding=ROUND_HALF_UP),
        amount=_to_cents(full_award * fraction),
        breakdown=breakdown,
        applied_articles=sorted(articles),
    )
