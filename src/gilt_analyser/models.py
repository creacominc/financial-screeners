from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Gilt:
    isin: str
    name: str
    coupon_rate: Decimal
    maturity_date: date
    clean_buy_price: Decimal
    redemption_value: Decimal = Decimal("100")


@dataclass(frozen=True)
class CashFlow:
    payment_date: date
    coupon: Decimal = Decimal("0")
    redemption: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.coupon + self.redemption


@dataclass(frozen=True)
class Analysis:
    gilt: Gilt
    settlement_date: date
    investment_budget: Decimal
    dealing_fee: Decimal
    accrued_interest_per_100: Decimal
    dirty_price_per_100: Decimal
    nominal_purchased: Decimal
    clean_consideration: Decimal
    accrued_interest_paid: Decimal
    purchase_consideration: Decimal
    total_initial_cost: Decimal
    unused_cash: Decimal
    coupon_income: Decimal
    redemption_proceeds: Decimal
    cgt_exempt_redemption_gain: Decimal
    total_proceeds: Decimal
    total_cash_profit: Decimal
    annualised_yield: Decimal
    cashflows: tuple[CashFlow, ...]

