"""Market-specific default settlement dates for screening reports."""
from datetime import date, timedelta
import holidays


def next_trading_day(today: date, market: str) -> date:
    """Return the next weekday not on the relevant market holiday calendar."""
    if market == "UK":
        closed = holidays.UK(years=[today.year, today.year + 1], subdiv="ENG")
    elif market == "US":
        closed = holidays.financial_holidays("NYSE", years=[today.year, today.year + 1])
    else:
        raise ValueError(f"Unsupported market: {market}")
    day = today + timedelta(days=1)
    while day.weekday() >= 5 or day in closed:
        day += timedelta(days=1)
    return day
