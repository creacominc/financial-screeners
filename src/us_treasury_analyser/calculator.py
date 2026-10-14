import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN

from gilt_analyser.calculator import annualised_yield
from gilt_analyser.models import CashFlow


@dataclass(frozen=True)
class Treasury:
    cusip: str
    name: str
    security_type: str
    coupon_rate: Decimal
    maturity_date: date
    clean_buy_price: Decimal
    minimum_nominal: Decimal = Decimal("1000")
    nominal_increment: Decimal = Decimal("1000")
    quote_date: str = ""
    price_source: str = ""
    maximum_nominal: Decimal | None = None
    broker_ytm_pct: Decimal | None = None
    security_id: str = ""
    quote_status: str = "supplied"
    quantity_basis: str = "configured"
    source_ask_quote: str = ""
    source_ask_yield_pct: Decimal | None = None
    price_basis: str = "Supplied clean offer price"
    price_settlement_date: str = ""
    fetched_at_utc: str = ""

    @property
    def identifier(self) -> str:
        return self.cusip or self.security_id


class UnaffordableTreasury(ValueError):
    """Valid offer whose minimum quantity exceeds the supplied budget."""


@dataclass(frozen=True)
class Analysis:
    treasury: Treasury
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


def validate(treasury: Treasury) -> None:
    if not treasury.name.strip() or (not treasury.cusip.strip() and not (
            treasury.security_id.strip() and treasury.quote_status == "indicative")):
        raise ValueError("CUSIP and name must not be empty; indicative rows require a security_id")
    if treasury.security_type not in {"bill", "note", "bond", "note_or_bond"}:
        raise ValueError("security_type must be bill, note, bond, or note_or_bond; TIPS, FRNs and STRIPS are unsupported")
    if treasury.quote_status not in {"supplied", "indicative"} or treasury.quantity_basis not in {"configured", "assumed"}:
        raise ValueError("invalid quote_status or quantity_basis")
    for label, value in (("coupon_rate", treasury.coupon_rate),
                         ("clean_buy_price", treasury.clean_buy_price),
                         ("minimum_nominal", treasury.minimum_nominal),
                         ("nominal_increment", treasury.nominal_increment)):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{label} must be a finite Decimal")
        if value < 0 or (label != "coupon_rate" and value == 0):
            raise ValueError(f"invalid {label}")
    if treasury.security_type == "bill" and treasury.coupon_rate != 0:
        raise ValueError("bills must have zero coupon_rate")
    if treasury.security_type != "bill" and treasury.coupon_rate == 0:
        raise ValueError("notes and bonds must have a positive coupon_rate")
    if treasury.quote_date:
        date.fromisoformat(treasury.quote_date)
    if treasury.price_settlement_date:
        date.fromisoformat(treasury.price_settlement_date)
    if treasury.maximum_nominal is not None:
        maximum = treasury.maximum_nominal
        if not isinstance(maximum, Decimal) or not maximum.is_finite() or maximum < treasury.minimum_nominal:
            raise ValueError("maximum_nominal must be a finite Decimal at least minimum_nominal")
    if treasury.broker_ytm_pct is not None:
        if not isinstance(treasury.broker_ytm_pct, Decimal) or not treasury.broker_ytm_pct.is_finite():
            raise ValueError("broker_ytm_pct must be a finite Decimal")
    if treasury.source_ask_yield_pct is not None:
        if not isinstance(treasury.source_ask_yield_pct, Decimal) or not treasury.source_ask_yield_pct.is_finite():
            raise ValueError("source_ask_yield_pct must be a finite Decimal")


def _coupon_date(maturity: date, periods: int) -> date:
    index = maturity.year * 12 + maturity.month - 1 - periods * 6
    year, month_index = divmod(index, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    # Treasury end-of-month coupons remain at month end, including February.
    end_of_month = maturity.day == calendar.monthrange(maturity.year, maturity.month)[1]
    return date(year, month, last_day if end_of_month else min(maturity.day, last_day))


def coupon_schedule(treasury: Treasury, settlement: date) -> tuple[date, ...]:
    if settlement >= treasury.maturity_date:
        raise ValueError("settlement date must be before maturity")
    if treasury.security_type == "bill":
        return ()
    dates = []
    periods = 0
    while (current := _coupon_date(treasury.maturity_date, periods)) > settlement:
        dates.append(current)
        periods += 1
    return tuple(reversed(dates))


def accrued_interest(treasury: Treasury, settlement: date) -> Decimal:
    dates = coupon_schedule(treasury, settlement)
    if not dates:
        return Decimal("0")
    following = dates[0]
    previous = _coupon_date(treasury.maturity_date, len(dates))
    return treasury.coupon_rate / Decimal("2") * Decimal((settlement - previous).days) / Decimal((following - previous).days)


def analyse_treasury(treasury: Treasury, settlement: date, investment: Decimal, fee: Decimal) -> Analysis:
    validate(treasury)
    if treasury.price_settlement_date and date.fromisoformat(treasury.price_settlement_date) != settlement:
        raise ValueError("derived price settlement date differs from analysis; fetch quotes again for the new settlement date")
    if not isinstance(investment, Decimal) or not investment.is_finite() or investment <= 0:
        raise ValueError("investment must be a positive finite Decimal")
    if not isinstance(fee, Decimal) or not fee.is_finite() or fee < 0 or fee >= investment:
        raise ValueError("fee must be non-negative, finite and less than investment")
    accrued = accrued_interest(treasury, settlement)
    dirty = treasury.clean_buy_price + accrued
    affordable = (investment - fee) * Decimal("100") / dirty
    if affordable < treasury.minimum_nominal:
        raise UnaffordableTreasury(f"investment is too small for calculation minimum_nominal of {treasury.identifier}")
    if treasury.maximum_nominal is not None:
        affordable = min(affordable, treasury.maximum_nominal)
    steps = ((affordable - treasury.minimum_nominal) / treasury.nominal_increment).to_integral_value(rounding=ROUND_DOWN)
    nominal = treasury.minimum_nominal + steps * treasury.nominal_increment
    clean = nominal * treasury.clean_buy_price / Decimal("100")
    accrued_paid = nominal * accrued / Decimal("100")
    initial = clean + accrued_paid + fee
    # Guard against Decimal division rounding at an affordability boundary.
    if initial > investment:
        nominal -= treasury.nominal_increment
        if nominal < treasury.minimum_nominal:
            raise UnaffordableTreasury("investment is too small after rounding")
        clean = nominal * treasury.clean_buy_price / Decimal("100")
        accrued_paid = nominal * accrued / Decimal("100")
        initial = clean + accrued_paid + fee
    coupon = nominal * treasury.coupon_rate / Decimal("200")
    dates = coupon_schedule(treasury, settlement)
    if treasury.security_type == "bill":
        flows = (CashFlow(treasury.maturity_date, redemption=nominal),)
    else:
        flows = tuple(CashFlow(day, coupon, nominal if day == treasury.maturity_date else Decimal("0")) for day in dates)
    income = sum((flow.coupon for flow in flows), Decimal("0"))
    proceeds = income + nominal
    return Analysis(treasury, settlement, investment, fee, accrued, dirty, nominal,
                    clean, accrued_paid, initial, investment - initial, income,
                    nominal, nominal - clean, proceeds, proceeds - initial,
                    annualised_yield(initial, flows, settlement), flows)
