from datetime import date
from decimal import Decimal

import pytest

from gilt_analyser.calculator import analyse_gilt, annualised_yield
from gilt_analyser.models import CashFlow, Gilt


def test_one_year_zero_coupon_yield_is_exact() -> None:
    flows = (CashFlow(date(2027, 1, 1), redemption=Decimal("105")),)
    assert annualised_yield(Decimal("100"), flows, date(2026, 1, 1)) == pytest.approx(Decimal("0.05"), abs=Decimal("1e-12"))


def test_analysis_includes_fee_and_separates_coupon_from_gain() -> None:
    gilt = Gilt("TEST", "Treasury 2%", Decimal("2"), date(2027, 1, 1), Decimal("98"))
    result = analyse_gilt(gilt, date(2026, 1, 1), Decimal("1000"), Decimal("10"))
    assert result.accrued_interest_per_100 == 0
    assert result.dirty_price_per_100 == Decimal("98")
    assert result.nominal_purchased == Decimal("1010.20")
    assert result.total_initial_cost <= Decimal("1000")
    assert result.coupon_income == Decimal("20.2040")
    assert result.redemption_proceeds == Decimal("1010.20")
    assert result.cgt_exempt_redemption_gain == result.redemption_proceeds - result.clean_consideration
    assert result.total_cash_profit == result.total_proceeds - result.total_initial_cost


def test_accrued_interest_is_part_of_purchase_cost() -> None:
    gilt = Gilt("TEST", "Treasury 4%", Decimal("4"), date(2027, 7, 22), Decimal("100"))
    result = analyse_gilt(gilt, date(2026, 10, 22), Decimal("5000"), Decimal("11.95"))
    assert result.accrued_interest_paid > 0
    assert result.purchase_consideration == result.clean_consideration + result.accrued_interest_paid
    assert result.total_initial_cost == result.purchase_consideration + result.dealing_fee


def test_fee_must_be_less_than_budget() -> None:
    gilt = Gilt("TEST", "Treasury 2%", Decimal("2"), date(2027, 1, 1), Decimal("98"))
    with pytest.raises(ValueError, match="less than investment"):
        analyse_gilt(gilt, date(2026, 1, 1), Decimal("10"), Decimal("10"))

