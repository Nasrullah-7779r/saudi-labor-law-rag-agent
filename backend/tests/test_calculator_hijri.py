"""Hijri (Umm al-Qura) service-period counting, Saudi Labor Law Art. 10."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hijridate import Hijri
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


def _h(year: int, month: int, day: int) -> date:
    """Gregorian date of a Hijri date (conversion only; expectations are by hand)."""
    g = Hijri(year, month, day).to_gregorian()
    return date(g.year, g.month, g.day)


def test_calendar_defaults_to_hijri():
    req = EndOfServiceRequest(
        last_monthly_wage=WAGE,
        start_date=_h(1440, 1, 1),
        end_date=_h(1445, 1, 1),
        reason=R.EMPLOYER_TERMINATION,
    )
    assert req.calendar is ServiceCalendar.HIJRI
    assert calculate_end_of_service(req).calendar is ServiceCalendar.HIJRI


def test_exact_hijri_anniversary_is_whole_years_but_gregorian_is_shorter():
    start, end = _h(1440, 1, 1), _h(1445, 1, 1)
    assert service_years(start, end, ServiceCalendar.HIJRI) == Decimal(5)
    # 5 Hijri years are ~54 days shorter than 5 Gregorian years.
    assert service_years(start, end, ServiceCalendar.GREGORIAN) < Decimal(5)


def test_resignation_band_differs_by_calendar():
    start = _h(1440, 1, 1)
    end = _h(1445, 1, 1) + timedelta(days=1)  # one day over 5 Hijri years

    def resign(calendar: ServiceCalendar):
        return calculate_end_of_service(
            EndOfServiceRequest(
                last_monthly_wage=WAGE,
                start_date=start,
                end_date=end,
                reason=R.RESIGNATION,
                calendar=calendar,
            )
        )

    hijri, gregorian = resign(ServiceCalendar.HIJRI), resign(ServiceCalendar.GREGORIAN)
    assert service_years(start, end, ServiceCalendar.HIJRI) > 5  # result field is rounded
    assert hijri.entitlement_fraction == Decimal("0.6667")  # over five years -> 2/3
    assert service_years(start, end, ServiceCalendar.GREGORIAN) < 5
    assert gregorian.entitlement_fraction == Decimal("0.3333")  # five years or less -> 1/3


def test_hijri_day_30_rolls_back_to_day_29_in_short_month():
    # 1420-02 has 30 days; 1423-02 has 29 (checked below via month_length()).
    assert Hijri(1420, 2, 1).month_length() == 30
    assert Hijri(1423, 2, 1).month_length() == 29
    start = _h(1420, 2, 30)
    anniversary = _h(1423, 2, 29)
    assert service_years(start, anniversary) == Decimal(3)
    assert service_years(start, anniversary - timedelta(days=1)) < Decimal(3)


@pytest.mark.parametrize(
    ("anniversary_year", "year_days"),
    [(1442, 354), (1443, 355)],  # Hijri year 1442 has 354 days, 1443 has 355
)
def test_partial_hijri_year_is_days_since_anniversary_over_hijri_year_length(
    anniversary_year: int, year_days: int
):
    start = _h(1440, 1, 1)
    last_anniversary = _h(anniversary_year, 1, 1)
    assert (_h(anniversary_year + 1, 1, 1) - last_anniversary).days == year_days
    whole = anniversary_year - 1440
    end = last_anniversary + timedelta(days=100)
    assert service_years(start, end) == Decimal(whole) + Decimal(100) / Decimal(year_days)


def test_out_of_range_hijri_dates_fail_validation_but_gregorian_accepted():
    kwargs = {
        "last_monthly_wage": WAGE,
        "start_date": date(1920, 1, 1),
        "end_date": date(2080, 1, 1),
        "reason": R.EMPLOYER_TERMINATION,
    }
    with pytest.raises(ValidationError):
        EndOfServiceRequest(**kwargs)
    with pytest.raises(ValidationError):
        EndOfServiceRequest(**kwargs, calendar=ServiceCalendar.HIJRI)
    req = EndOfServiceRequest(**kwargs, calendar=ServiceCalendar.GREGORIAN)
    assert req.calendar is ServiceCalendar.GREGORIAN


def test_full_amount_for_exactly_seven_hijri_years():
    # 5 * 0.5 * 10000 + 2 * 10000 = 45000
    result = calculate_end_of_service(
        EndOfServiceRequest(
            last_monthly_wage=WAGE,
            start_date=_h(1440, 1, 1),
            end_date=_h(1447, 1, 1),
            reason=R.EMPLOYER_TERMINATION,
        )
    )
    assert result.calendar is ServiceCalendar.HIJRI
    assert result.service_years == Decimal("7.00")
    assert result.amount == Decimal("45000.00")
    assert result.applied_articles == [84]
