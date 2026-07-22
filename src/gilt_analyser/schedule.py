import calendar
from datetime import date
from decimal import Decimal

from .models import Gilt


def _shift_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def coupon_dates(gilt: Gilt, settlement: date) -> list[date]:
    """Return coupon dates strictly after settlement through maturity."""
    dates: list[date] = []
    periods = 0
    current = gilt.maturity_date
    while current > settlement:
        dates.append(current)
        periods += 1
        current = _shift_months(gilt.maturity_date, -6 * periods)
    return sorted(dates)


def surrounding_coupon_dates(gilt: Gilt, settlement: date) -> tuple[date, date]:
    periods = 0
    next_coupon = gilt.maturity_date
    previous_coupon = _shift_months(gilt.maturity_date, -6)
    while previous_coupon > settlement:
        periods += 1
        next_coupon = previous_coupon
        previous_coupon = _shift_months(gilt.maturity_date, -6 * (periods + 1))
    if settlement == next_coupon:
        previous_coupon = next_coupon
        next_coupon = _shift_months(gilt.maturity_date, -6 * (periods - 1))
    return previous_coupon, next_coupon


def accrued_interest_per_100(gilt: Gilt, settlement: date) -> Decimal:
    if settlement >= gilt.maturity_date:
        raise ValueError("settlement date must be before maturity")
    previous_coupon, next_coupon = surrounding_coupon_dates(gilt, settlement)
    elapsed = Decimal((settlement - previous_coupon).days)
    period = Decimal((next_coupon - previous_coupon).days)
    semiannual_coupon = gilt.redemption_value * gilt.coupon_rate / Decimal("200")
    return semiannual_coupon * elapsed / period
