import csv
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from gilt_analyser.calculator import analyse_gilt
from gilt_analyser.models import Gilt
from gilt_analyser.reporting import read_gilts, write_reports


def test_read_and_write_ranked_reports(tmp_path) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "isin,name,coupon_rate,maturity_date,clean_buy_price\n"
        "LOW,Low return,0,2027-01-01,100\n"
        "HIGH,High return,0,2027-01-01,95\n",
        encoding="utf-8",
    )
    analyses = [analyse_gilt(g, date(2026, 1, 1), Decimal("1000"), Decimal("0")) for g in read_gilts(source)]
    csv_path, xlsx_path = write_reports(analyses, tmp_path / "comparison")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["isin"] for row in rows] == ["HIGH", "LOW"]
    assert rows[0]["cgt_exempt_redemption_gain"] != ""
    workbook = load_workbook(xlsx_path, read_only=True)
    assert workbook["Gilt comparison"]["B2"].value == "HIGH"

