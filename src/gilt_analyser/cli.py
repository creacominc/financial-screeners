import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .calculator import analyse_gilt
from .reporting import read_gilts, write_reports


def decimal_argument(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(f"invalid decimal amount: {value}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare conventional UK gilts held to maturity")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--investment", required=True, type=decimal_argument, help="cash budget per gilt, in GBP")
    parser.add_argument("--fee", type=decimal_argument, default=Decimal("11.95"), help="HL dealing fee per purchase")
    parser.add_argument("--settlement-date", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (default: today)")
    parser.add_argument("--output", type=Path, default=Path("reports/gilt-comparison"), help="output filename prefix")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analyses = [analyse_gilt(gilt, args.settlement_date, args.investment, args.fee) for gilt in read_gilts(args.input_csv)]
    csv_path, xlsx_path = write_reports(analyses, args.output)
    print(f"Wrote {csv_path} and {xlsx_path}")


if __name__ == "__main__":
    main()

