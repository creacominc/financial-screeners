from datetime import date
from decimal import Decimal, ROUND_DOWN, localcontext

from .models import Analysis, CashFlow, Gilt
from .schedule import accrued_interest_per_100, coupon_dates

ONE_CENT = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


def _xnpv(rate: Decimal, initial: Decimal, flows: tuple[CashFlow, ...], start: date) -> Decimal:
    base = Decimal("1") + rate
    if base <= 0:
        raise ValueError("yield must be greater than -100%")
    with localcontext() as context:
        context.prec = 40
        value = -initial
        for flow in flows:
            years = Decimal((flow.payment_date - start).days) / Decimal("365")
            value += flow.total / (base ** years)
        return value


def annualised_yield(initial: Decimal, flows: tuple[CashFlow, ...], start: date) -> Decimal:
    """Solve annual effective XIRR using Actual/365 date exponents."""
    if initial <= 0 or not flows or sum((f.total for f in flows), Decimal("0")) <= 0:
        raise ValueError("positive initial cost and proceeds are required")
    low, high = Decimal("-0.999999"), Decimal("1")
    low_value = _xnpv(low, initial, flows, start)
    high_value = _xnpv(high, initial, flows, start)
    while high_value > 0 and high < Decimal("1000000"):
        high *= 2
        high_value = _xnpv(high, initial, flows, start)
    if low_value * high_value > 0:
        raise ValueError("could not bracket annualised yield")
    for _ in range(240):
        middle = (low + high) / 2
        value = _xnpv(middle, initial, flows, start)
        if abs(value) < Decimal("0.000000000001"):
            return middle
        if value > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def analyse_gilt(gilt: Gilt, settlement: date, investment: Decimal, fee: Decimal) -> Analysis:
    if investment <= 0:
        raise ValueError("investment must be positive")
    if fee < 0 or fee >= investment:
        raise ValueError("fee must be non-negative and less than investment")

    accrued_100 = accrued_interest_per_100(gilt, settlement)
    dirty_100 = gilt.clean_buy_price + accrued_100
    nominal = (((investment - fee) * ONE_HUNDRED / dirty_100).quantize(ONE_CENT, rounding=ROUND_DOWN))
    if nominal <= 0:
        raise ValueError("investment is too small to purchase this gilt after the fee")

    clean = nominal * gilt.clean_buy_price / ONE_HUNDRED
    accrued_paid = nominal * accrued_100 / ONE_HUNDRED
    consideration = clean + accrued_paid
    initial_cost = consideration + fee
    unused = investment - initial_cost
    coupon_each = nominal * gilt.redemption_value * gilt.coupon_rate / Decimal("20000")

    flows: list[CashFlow] = []
    for payment_date in coupon_dates(gilt, settlement):
        redemption = nominal * gilt.redemption_value / ONE_HUNDRED if payment_date == gilt.maturity_date else Decimal("0")
        flows.append(CashFlow(payment_date, coupon_each, redemption))
    cashflows = tuple(flows)
    coupon_income = coupon_each * Decimal(len(cashflows))
    redemption = nominal * gilt.redemption_value / ONE_HUNDRED
    redemption_gain = redemption - clean
    proceeds = coupon_income + redemption
    profit = proceeds - initial_cost

    return Analysis(
        gilt, settlement, investment, fee, accrued_100, dirty_100, nominal,
        clean, accrued_paid, consideration, initial_cost, unused,
        coupon_income, redemption, redemption_gain, proceeds, profit,
        annualised_yield(initial_cost, cashflows, settlement), cashflows,
    )

