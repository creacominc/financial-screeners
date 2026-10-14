"""Public, indicative Treasury quotes. These are not Schwab dealing offers."""
import argparse
import calendar
import csv
import json
import re
import ssl
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

from .calculator import Treasury, validate

WSJ_URL = "https://www.wsj.com/market-data/bonds/treasuries"
INPUT_FIELDS = (
    "cusip", "security_id", "name", "security_type", "coupon_rate", "maturity_date",
    "clean_buy_price", "minimum_nominal", "nominal_increment", "maximum_nominal",
    "broker_ytm_pct", "quote_date", "price_source", "quote_status", "quantity_basis",
    "source_ask_quote", "source_ask_yield_pct", "price_basis", "price_settlement_date",
    "fetched_at_utc",
)


def extract_tables(html: str) -> dict:
    marker = "window.__STATE__ = "
    if marker not in html:
        raise ValueError("WSJ page has no embedded quote data; page layout may have changed")
    try:
        state, _ = json.JSONDecoder(parse_float=Decimal).raw_decode(html.split(marker, 1)[1])
        tables = {}
        for key, entry in state["data"].items():
            if key.startswith("mdc_treasury_"):
                kind = json.loads(entry["data"]["id"])["treasury"]
                table = entry["data"]["data"]
                if kind in tables:
                    raise ValueError("duplicate WSJ Treasury table")
                if not isinstance(table.get("instruments"), list) or not table["instruments"] or not table.get("timestamp"):
                    raise ValueError(f"WSJ {kind} table is empty or undated")
                tables[kind] = table
        if set(tables) != {"NOTES_AND_BONDS", "BILLS"}:
            raise ValueError("WSJ page is missing a Treasury table")
        return tables
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("WSJ structured quote data is invalid") from error


def treasury_fractional_price(value: str) -> Decimal:
    """WSJ 99.0320 = cash-market 99-032 = 99 + 3/32 + 2/256.

    The WSJ fourth fractional digit is padding, not a decimal-price digit.
    Reject unknown formats instead of guessing their units.
    """
    if not isinstance(value, str):
        raise ValueError("Treasury fractional quote must be text")
    match = re.fullmatch(r"(\d+)\.(\d{2})([0-7])0", value.strip())
    if not match or int(match[2]) > 31:
        raise ValueError(f"invalid WSJ Treasury fractional price: {value}")
    price = Decimal(match[1]) + Decimal(match[2]) / Decimal("32") + Decimal(match[3]) / Decimal("256")
    if price <= 0:
        raise ValueError("Treasury ask price must be positive")
    return price


def bill_price(discount_rate_pct: Decimal, settlement: date, maturity: date) -> Decimal:
    """Implied price per $100 at requested settlement, from bank discount %.

    TreasuryDirect: face * (1 - discount_fraction * actual_days / 360).
    Keep full precision; broker/auction cash rounding is not applied.
    """
    if not isinstance(discount_rate_pct, Decimal) or not discount_rate_pct.is_finite():
        raise ValueError("bill discount rate must be a finite Decimal")
    if maturity <= settlement:
        raise ValueError("bill settlement must be before maturity")
    price = Decimal("100") - discount_rate_pct * Decimal((maturity - settlement).days) / Decimal("360")
    if price <= 0:
        raise ValueError("bill discount rate implies a non-positive price")
    return price


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise ValueError(f"{label} must contain a decimal value")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def parse_treasuries(tables: dict, settlement: date, months: int = 24,
                     max_quote_age_days: int = 7, fetched_at_utc: str = "") -> list[Treasury]:
    if months < 1 or max_quote_age_days < 0:
        raise ValueError("months must be positive and max_quote_age_days non-negative")
    cutoff = _add_months(settlement, months)
    securities, seen = [], set()
    for kind in ("BILLS", "NOTES_AND_BONDS"):
        try:
            table = tables[kind]
            quote_date = datetime.strptime(table["timestamp"], "%A, %B %d, %Y").date()
            age = (settlement - quote_date).days
            if age < 0 or age > max_quote_age_days:
                raise ValueError(f"WSJ {kind} quote date {quote_date} is outside the allowed age of {max_quote_age_days} days before settlement {settlement}")
            for row in table["instruments"]:
                maturity = datetime.strptime(row["maturityDate"], "%m/%d/%Y").date()
                if not settlement < maturity <= cutoff:
                    continue
                coupon = Decimal("0") if kind == "BILLS" else _decimal(row["coupon"], "coupon")
                source_ask = row["ask"]
                source_yield = _decimal(row["askYield"], "ask yield")
                if kind == "BILLS":
                    price = bill_price(_decimal(source_ask, "ask discount rate"), settlement, maturity)
                    security_type = "bill"
                    price_basis = "Implied from ask discount rate at analysis settlement (Actual/360)"
                    price_settlement = settlement.isoformat()
                    name = f"US Treasury bill {maturity}"
                else:
                    price = treasury_fractional_price(source_ask)
                    security_type = "note_or_bond"
                    price_basis = "Clean ask converted from Treasury 32nds and eighths"
                    price_settlement = ""
                    name = f"US Treasury {coupon}% {maturity}"
                reference = f"WSJ:{security_type}:{maturity}:{coupon}"
                if reference in seen:
                    raise ValueError(f"ambiguous duplicate WSJ security terms: {reference}")
                seen.add(reference)
                security = Treasury(
                    cusip="", name=name, security_type=security_type,
                    coupon_rate=coupon, maturity_date=maturity, clean_buy_price=price,
                    quote_date=quote_date.isoformat(), price_source="WSJ / Tullett Prebon",
                    security_id=reference, quote_status="indicative", quantity_basis="assumed",
                    source_ask_quote=str(source_ask), source_ask_yield_pct=source_yield,
                    price_basis=price_basis, price_settlement_date=price_settlement,
                    fetched_at_utc=fetched_at_utc,
                )
                validate(security)
                securities.append(security)
        except (KeyError, TypeError, ArithmeticError) as error:
            raise ValueError(f"invalid WSJ {kind} quote data: {error}") from error
    if not securities:
        raise ValueError("WSJ returned no Treasuries in the requested maturity window")
    return securities


def fetch_treasuries(settlement: date, months: int = 24, max_quote_age_days: int = 7,
                     snapshot_path: Path | None = None) -> list[Treasury]:
    ca = Path("/etc/ssl/cert.pem")
    context = ssl.create_default_context(cafile=str(ca) if ca.is_file() else None)
    request = Request(WSJ_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
    with urlopen(request, timeout=30, context=context) as response:
        html = response.read().decode("utf-8")
    tables = extract_tables(html)
    fetched = datetime.now(timezone.utc).isoformat()
    securities = parse_treasuries(tables, settlement, months, max_quote_age_days, fetched)
    if snapshot_path:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps({"source_url": WSJ_URL, "fetched_at_utc": fetched,
                                             "tables": tables}, indent=2, default=str), encoding="utf-8")
    return securities


def write_input_csv(securities: list[Treasury], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INPUT_FIELDS)
        writer.writeheader()
        for security in securities:
            writer.writerow({key: getattr(security, key) for key in INPUT_FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public indicative WSJ Treasury quotes")
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True, help="analysis settlement date")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--max-quote-age-days", type=int, default=7)
    args = parser.parse_args()
    try:
        securities = fetch_treasuries(args.as_of, args.months, args.max_quote_age_days,
                                     args.output_csv.with_suffix(".source.json"))
        write_input_csv(securities, args.output_csv)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Wrote {len(securities)} indicative Treasury quotes to {args.output_csv}")


if __name__ == "__main__":
    main()
