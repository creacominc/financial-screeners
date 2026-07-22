from datetime import date
from decimal import Decimal

import pytest

from gilt_analyser.models import Gilt
from gilt_analyser.schedule import accrued_interest_per_100, coupon_dates


@pytest.fixture
def gilt() -> Gilt:
    return Gilt("TEST", "Treasury 4%", Decimal("4"), date(2027, 7, 22), Decimal("99"))


def test_coupon_schedule_runs_back_from_maturity(gilt: Gilt) -> None:
    assert coupon_dates(gilt, date(2026, 7, 23)) == [date(2027, 1, 22), date(2027, 7, 22)]


def test_month_end_schedule_stays_anchored_to_maturity() -> None:
    gilt = Gilt("TEST", "Month end", Decimal("1"), date(2027, 8, 31), Decimal("99"))
    assert coupon_dates(gilt, date(2026, 8, 30)) == [date(2026, 8, 31), date(2027, 2, 28), date(2027, 8, 31)]


def test_accrued_interest_uses_actual_days_in_coupon_period(gilt: Gilt) -> None:
    result = accrued_interest_per_100(gilt, date(2026, 10, 22))
    assert result == Decimal("2") * Decimal("92") / Decimal("184")


def test_accrued_interest_is_zero_on_coupon_date(gilt: Gilt) -> None:
    assert accrued_interest_per_100(gilt, date(2026, 7, 22)) == 0


def test_settlement_must_precede_maturity(gilt: Gilt) -> None:
    with pytest.raises(ValueError, match="before maturity"):
        accrued_interest_per_100(gilt, gilt.maturity_date)
