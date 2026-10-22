"""Market-specific default settlement dates for screening reports."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import holidays


def next_trading_day(today: date, market: str) -> date:
    """Return the next weekday not on the relevant market holiday calendar."""
    if market == "UK":
        closed = holidays.UK(years=[today.year, today.year + 1], subdiv="ENG")
    elif market == "US":
        # US bond trading also closes on Columbus Day and Veterans Day,
        # which are federal holidays but not NYSE holidays.
        closed = holidays.financial_holidays("NYSE", years=[today.year, today.year + 1])
        closed.update(holidays.US(years=[today.year, today.year + 1]))
    else:
        raise ValueError(f"Unsupported market: {market}")
    day = today + timedelta(days=1)
    while day.weekday() >= 5 or day in closed:
        day += timedelta(days=1)
    return day


def default_settlement_date(market: str) -> date:
    """Next market trading date after today's London date; a model assumption."""
    return next_trading_day(datetime.now(ZoneInfo("Europe/London")).date(), market)
