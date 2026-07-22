import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from .models import Analysis, Gilt

INPUT_COLUMNS = ("isin", "name", "coupon_rate", "maturity_date", "clean_buy_price")


def read_gilts(path: Path) -> list[Gilt]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(INPUT_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"input CSV is missing columns: {', '.join(sorted(missing))}")
        gilts = []
        for line, row in enumerate(reader, start=2):
            try:
                gilts.append(Gilt(
                    isin=row["isin"].strip(), name=row["name"].strip(),
                    coupon_rate=Decimal(row["coupon_rate"].strip()),
                    maturity_date=date.fromisoformat(row["maturity_date"].strip()),
                    clean_buy_price=Decimal(row["clean_buy_price"].strip()),
                    redemption_value=Decimal((row.get("redemption_value") or "100").strip()),
                ))
            except (ValueError, ArithmeticError) as error:
                raise ValueError(f"invalid input on CSV line {line}: {error}") from error
    return gilts


COLUMNS = (
    "rank", "isin", "name", "coupon_rate_pct", "maturity_date", "settlement_date",
    "clean_buy_price_per_100", "accrued_interest_per_100", "dirty_price_per_100",
    "investment_budget", "dealing_fee", "nominal_purchased", "clean_consideration",
    "accrued_interest_paid", "total_initial_cost", "unused_cash", "coupon_income",
    "redemption_proceeds", "cgt_exempt_redemption_gain", "total_proceeds",
    "total_cash_profit", "net_annualised_return_pct",
)


def _row(rank: int, item: Analysis) -> dict[str, object]:
    return {
        "rank": rank, "isin": item.gilt.isin, "name": item.gilt.name,
        "coupon_rate_pct": item.gilt.coupon_rate, "maturity_date": item.gilt.maturity_date,
        "settlement_date": item.settlement_date,
        "clean_buy_price_per_100": item.gilt.clean_buy_price,
        "accrued_interest_per_100": item.accrued_interest_per_100,
        "dirty_price_per_100": item.dirty_price_per_100,
        "investment_budget": item.investment_budget, "dealing_fee": item.dealing_fee,
        "nominal_purchased": item.nominal_purchased, "clean_consideration": item.clean_consideration,
        "accrued_interest_paid": item.accrued_interest_paid, "total_initial_cost": item.total_initial_cost,
        "unused_cash": item.unused_cash, "coupon_income": item.coupon_income,
        "redemption_proceeds": item.redemption_proceeds,
        "cgt_exempt_redemption_gain": item.cgt_exempt_redemption_gain,
        "total_proceeds": item.total_proceeds, "total_cash_profit": item.total_cash_profit,
        "net_annualised_return_pct": item.annualised_yield * Decimal("100"),
    }


def ranked_rows(analyses: list[Analysis]) -> list[dict[str, object]]:
    ordered = sorted(analyses, key=lambda item: item.annualised_yield, reverse=True)
    return [_row(rank, item) for rank, item in enumerate(ordered, start=1)]


def write_reports(analyses: list[Analysis], output_prefix: Path) -> tuple[Path, Path]:
    rows = ranked_rows(analyses)
    csv_path = output_prefix.with_suffix(".csv")
    xlsx_path = output_prefix.with_suffix(".xlsx")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: str(value) if isinstance(value, (Decimal, date)) else value for key, value in row.items()})

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Gilt comparison"
    sheet.append(list(COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([float(value) if isinstance(value, Decimal) else value for value in row.values()])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["B"].width = 16
    sheet.column_dimensions["C"].width = 34
    for column in range(4, len(COLUMNS) + 1):
        for cell in sheet.iter_cols(min_col=column, max_col=column, min_row=2):
            for value in cell:
                if isinstance(value.value, float):
                    value.number_format = "0.0000"
    workbook.save(xlsx_path)
    return csv_path, xlsx_path
