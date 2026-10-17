import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN

from gilt_analyser.calculator import annualised_yield
from gilt_analyser.models import CashFlow


@dataclass(frozen=True)
class CorporateBond:
    cusip: str
    name: str
    coupon_rate: Decimal
    maturity_date: date
    clean_buy_price: Decimal
    accrued_interest_per_100: Decimal
    price_settlement_date: str
    moodys: str
    sp: str
    ratings_date: str
    currency: str
    terms: str
    minimum_nominal: Decimal = Decimal("1000")
    nominal_increment: Decimal = Decimal("1000")
    quote_date: str = ""
    price_source: str = ""
    maximum_nominal: Decimal | None = None
    broker_ytm_pct: Decimal | None = None
    broker_ytw_pct: Decimal | None = None
    source_selected_nominal: Decimal | None = None
    source_accrued_interest: Decimal | None = None
    source_estimated_total: Decimal | None = None


class UnaffordableCorporateBond(ValueError):
    """Valid offer whose minimum quantity exceeds the supplied budget."""


@dataclass(frozen=True)
class Analysis:
    bond: CorporateBond
    settlement_date: date
    investment_budget: Decimal
    dealing_fee: Decimal
    accrued_interest_per_100: Decimal
    dirty_price_per_100: Decimal
    nominal_purchased: Decimal
    clean_consideration: Decimal
    accrued_interest_paid: Decimal
    total_initial_cost: Decimal
    unused_cash: Decimal
    coupon_income: Decimal
    redemption_proceeds: Decimal
    redemption_gain: Decimal
    total_proceeds: Decimal
    total_cash_profit: Decimal
    annualised_yield: Decimal
    cashflows: tuple[CashFlow, ...]


def validate(bond: CorporateBond) -> None:
    if not bond.name.strip() or len(bond.cusip) != 9 or not bond.cusip.isalnum():
        raise ValueError("CUSIP must have nine alphanumeric characters and name must not be empty")
    for label, value in (("coupon_rate", bond.coupon_rate),
                         ("clean_buy_price", bond.clean_buy_price),
                         ("minimum_nominal", bond.minimum_nominal),
                         ("nominal_increment", bond.nominal_increment)):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{label} must be a finite Decimal")
        if value < 0 or (label != "coupon_rate" and value == 0):
            raise ValueError(f"invalid {label}")
    if not isinstance(bond.accrued_interest_per_100, Decimal) or not bond.accrued_interest_per_100.is_finite() or bond.accrued_interest_per_100 < 0:
        raise ValueError("accrued_interest_per_100 must be finite and non-negative")
    if not bond.price_settlement_date or not bond.quote_date or not bond.price_source:
        raise ValueError("quote_date, price_source and price_settlement_date are required")
    date.fromisoformat(bond.ratings_date)
    if bond.quote_date:
        date.fromisoformat(bond.quote_date)
    if bond.price_settlement_date:
        date.fromisoformat(bond.price_settlement_date)
    if bond.maximum_nominal is not None:
        maximum = bond.maximum_nominal
        if not isinstance(maximum, Decimal) or not maximum.is_finite() or maximum < bond.minimum_nominal:
            raise ValueError("maximum_nominal must be a finite Decimal at least minimum_nominal")
    if bond.broker_ytm_pct is not None:
        if not isinstance(bond.broker_ytm_pct, Decimal) or not bond.broker_ytm_pct.is_finite():
            raise ValueError("broker_ytm_pct must be a finite Decimal")

    for key in ('broker_ytw_pct', 'source_selected_nominal', 'source_accrued_interest', 'source_estimated_total'):
        value = getattr(bond, key)
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            raise ValueError(f'{key} must be a finite Decimal')


def _coupon_date(maturity: date, periods: int) -> date:
    index = maturity.year * 12 + maturity.month - 1 - periods * 6
    year, month_index = divmod(index, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(maturity.day, last_day))


def coupon_schedule(bond: CorporateBond, settlement: date) -> tuple[date, ...]:
    if settlement >= bond.maturity_date:
        raise ValueError("settlement date must be before maturity")
    dates = []
    periods = 0
    while (current := _coupon_date(bond.maturity_date, periods)) > settlement:
        dates.append(current)
        periods += 1
    return tuple(reversed(dates))


def accrued_interest(bond: CorporateBond, settlement: date) -> Decimal:
    dates = coupon_schedule(bond, settlement)
    previous = _coupon_date(bond.maturity_date, len(dates))
    accrued = bond.accrued_interest_per_100
    if settlement == previous and accrued != 0:
        raise ValueError("coupon-date accrued interest must be zero")
    if accrued > bond.coupon_rate / Decimal("2"):
        raise ValueError("accrued interest exceeds one regular coupon")
    return accrued


def analyse_bond(bond: CorporateBond, settlement: date, investment: Decimal, fee: Decimal) -> Analysis:
    validate(bond)
    from .screening import SUPPORTED_TERMS
    if bond.currency != 'USD' or bond.terms != SUPPORTED_TERMS or bond.coupon_rate <= 0:
        raise ValueError('Unsupported corporate bond terms')
    if bond.price_settlement_date and date.fromisoformat(bond.price_settlement_date) != settlement:
        raise ValueError("broker accrual settlement date differs from analysis; obtain updated broker accrual")
    if not isinstance(investment, Decimal) or not investment.is_finite() or investment <= 0:
        raise ValueError("investment must be a positive finite Decimal")
    if not isinstance(fee, Decimal) or not fee.is_finite() or fee < 0 or fee >= investment:
        raise ValueError("fee must be non-negative, finite and less than investment")
    accrued = accrued_interest(bond, settlement)
    dirty = bond.clean_buy_price + accrued
    affordable = (investment - fee) * Decimal("100") / dirty
    if affordable < bond.minimum_nominal:
        raise UnaffordableCorporateBond(f"investment is too small for calculation minimum_nominal of {bond.cusip}")
    if bond.maximum_nominal is not None:
        affordable = min(affordable, bond.maximum_nominal)
    steps = ((affordable - bond.minimum_nominal) / bond.nominal_increment).to_integral_value(rounding=ROUND_DOWN)
    nominal = bond.minimum_nominal + steps * bond.nominal_increment
    clean = nominal * bond.clean_buy_price / Decimal("100")
    accrued_paid = nominal * accrued / Decimal("100")
    initial = clean + accrued_paid + fee
    # Guard against Decimal division rounding at an affordability boundary.
    if initial > investment:
        nominal -= bond.nominal_increment
        if nominal < bond.minimum_nominal:
            raise UnaffordableCorporateBond("investment is too small after rounding")
        clean = nominal * bond.clean_buy_price / Decimal("100")
        accrued_paid = nominal * accrued / Decimal("100")
        initial = clean + accrued_paid + fee
    coupon = nominal * bond.coupon_rate / Decimal("200")
    dates = coupon_schedule(bond, settlement)
    flows = tuple(CashFlow(day, coupon, nominal if day == bond.maturity_date else Decimal("0")) for day in dates)
    income = sum((flow.coupon for flow in flows), Decimal("0"))
    proceeds = income + nominal
    return Analysis(bond, settlement, investment, fee, accrued, dirty, nominal,
                    clean, accrued_paid, initial, investment - initial, income,
                    nominal, nominal - clean, proceeds, proceeds - initial,
                    annualised_yield(initial, flows, settlement), flows)
