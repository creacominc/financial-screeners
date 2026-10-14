import csv
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from .calculator import Analysis, Treasury, validate

INPUT_COLUMNS = ("cusip", "name", "security_type", "coupon_rate", "maturity_date", "clean_buy_price")
COLUMNS = (
    "rank", "cusip", "security_id", "name", "security_type", "currency", "quote_status", "months_to_maturity",
    "net_annualised_return_pct", "coupon_rate_pct", "maturity_date", "settlement_date",
    "clean_buy_price_per_100", "accrued_interest_per_100", "dirty_price_per_100",
    "investment_budget", "dealing_fee", "nominal_purchased", "clean_consideration",
    "accrued_interest_paid", "total_initial_cost", "unused_cash", "coupon_income",
    "redemption_proceeds", "redemption_gain", "total_proceeds", "total_cash_profit",
    "minimum_nominal", "nominal_increment", "maximum_nominal", "broker_ytm_pct", "quote_date", "price_source",
    "quantity_basis", "analysis_minimum_nominal", "analysis_nominal_increment",
    "source_ask_quote", "source_ask_yield_pct", "price_basis", "price_settlement_date", "fetched_at_utc",
)


def read_treasuries(path: Path) -> list[Treasury]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(INPUT_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"input CSV is missing columns: {', '.join(sorted(missing))}")
        securities = []
        seen = set()
        for line, row in enumerate(reader, 2):
            try:
                if None in row:
                    raise ValueError("too many columns")
                treasury = Treasury(
                    cusip=row["cusip"].strip(), name=row["name"].strip(),
                    security_type=row["security_type"].strip().lower(),
                    coupon_rate=Decimal(row["coupon_rate"].strip()),
                    maturity_date=date.fromisoformat(row["maturity_date"].strip()),
                    clean_buy_price=Decimal(row["clean_buy_price"].strip()),
                    minimum_nominal=Decimal((row.get("minimum_nominal") or "1000").strip()),
                    nominal_increment=Decimal((row.get("nominal_increment") or "1000").strip()),
                    quote_date=(row.get("quote_date") or "").strip(),
                    price_source=(row.get("price_source") or "").strip(),
                    maximum_nominal=Decimal(row["maximum_nominal"].strip()) if (row.get("maximum_nominal") or "").strip() else None,
                    broker_ytm_pct=Decimal(row["broker_ytm_pct"].strip()) if (row.get("broker_ytm_pct") or "").strip() else None,
                    security_id=(row.get("security_id") or "").strip(),
                    quote_status=(row.get("quote_status") or "supplied").strip(),
                    quantity_basis=(row.get("quantity_basis") or "configured").strip(),
                    source_ask_quote=(row.get("source_ask_quote") or "").strip(),
                    source_ask_yield_pct=Decimal(row["source_ask_yield_pct"].strip()) if (row.get("source_ask_yield_pct") or "").strip() else None,
                    price_basis=(row.get("price_basis") or "Supplied clean offer price").strip(),
                    price_settlement_date=(row.get("price_settlement_date") or "").strip(),
                    fetched_at_utc=(row.get("fetched_at_utc") or "").strip(),
                )
                validate(treasury)
                if treasury.identifier in seen:
                    raise ValueError("duplicate security identifier")
                seen.add(treasury.identifier)
                securities.append(treasury)
            except (ValueError, ArithmeticError, AttributeError, TypeError) as error:
                raise ValueError(f"invalid input on CSV line {line}: {error}") from error
    if not securities:
        raise ValueError("input CSV contains no Treasuries")
    return securities


def ranked_rows(analyses: list[Analysis]) -> list[dict[str, object]]:
    ordered = sorted(analyses, key=lambda item: (
        -(item.annualised_yield / Decimal("0.001")).to_integral_value(rounding=ROUND_FLOOR),
        (item.treasury.maturity_date - item.settlement_date).days,
        -item.annualised_yield, item.treasury.identifier,
    ))
    rows = []
    for rank, item in enumerate(ordered, 1):
        security = item.treasury
        row = {key: getattr(item, key) for key in COLUMNS if hasattr(item, key)}
        row.update(rank=rank, cusip=security.cusip, security_id=security.security_id, name=security.name,
                   security_type=security.security_type, currency="USD",
                   quote_status=security.quote_status,
                   months_to_maturity=(Decimal((security.maturity_date - item.settlement_date).days) * Decimal("12") / Decimal("365")).quantize(Decimal("0.01")),
                   net_annualised_return_pct=item.annualised_yield * Decimal("100"),
                   coupon_rate_pct=security.coupon_rate, maturity_date=security.maturity_date,
                   clean_buy_price_per_100=security.clean_buy_price,
                   minimum_nominal=security.minimum_nominal if security.quantity_basis == "configured" else None,
                   nominal_increment=security.nominal_increment if security.quantity_basis == "configured" else None,
                   maximum_nominal=security.maximum_nominal, broker_ytm_pct=security.broker_ytm_pct,
                   quote_date=security.quote_date, price_source=security.price_source,
                   quantity_basis=security.quantity_basis,
                   analysis_minimum_nominal=security.minimum_nominal,
                   analysis_nominal_increment=security.nominal_increment,
                   source_ask_quote=security.source_ask_quote, source_ask_yield_pct=security.source_ask_yield_pct,
                   price_basis=security.price_basis, price_settlement_date=security.price_settlement_date,
                   fetched_at_utc=security.fetched_at_utc)
        rows.append(row)
    return rows


def write_reports(analyses: list[Analysis], prefix: Path) -> tuple[Path, Path]:
    rows = ranked_rows(analyses)
    csv_path, xlsx_path = prefix.with_suffix(".csv"), prefix.with_suffix(".xlsx")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "US Treasury comparison"
    sheet.append(list(COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[1].height = 32
    for row in rows:
        sheet.append([float(row[key]) if isinstance(row[key], Decimal) else row[key] for key in COLUMNS])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        key = cells[0].value
        sheet.column_dimensions[cells[0].column_letter].width = {
            "rank": 7, "cusip": 15, "security_id": 46, "name": 40,
            "price_source": 32, "price_basis": 75, "fetched_at_utc": 36,
        }.get(key, 24)
        for cell in cells[1:]:
            if isinstance(cell.value, float):
                cell.number_format = "0.0000"
    workbook.save(xlsx_path)
    return csv_path, xlsx_path
