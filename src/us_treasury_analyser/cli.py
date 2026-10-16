import argparse
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from gilt_analyser.cli import decimal_argument

from .calculator import UnaffordableTreasury, analyse_treasury
from .reporting import read_treasuries, write_reports, ranked_rows
from .wsj_fetcher import fetch_treasuries, write_input_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare US Treasury bills, fixed-rate notes and bonds held to maturity in USD")
    parser.add_argument("input_csv", type=Path, nargs="?", help="optional supplied quotes; omitted: fetch current indicative WSJ quotes")
    parser.add_argument("--fetch-wsj", action="store_true", help="explicitly fetch current indicative WSJ quotes")
    parser.add_argument("--months", type=int, default=24, help="fetch maturity window in calendar months (default: 24)")
    parser.add_argument("--max-quote-age-days", type=int, default=7, help="maximum published quote age before settlement (default: 7)")
    parser.add_argument("--investment", required=True, type=decimal_argument, help="USD budget per security")
    parser.add_argument("--fee", type=decimal_argument, default=Decimal("0"), help="USD dealing fee per purchase")
    parser.add_argument("--settlement-date", required=True, type=date.fromisoformat, help="actual settlement date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=Path("reports/us_treasuries"))
    parser.add_argument("--skip-unaffordable", action="store_true", help="report offers exceeding the budget in a separate exclusions CSV")
    args = parser.parse_args()
    if args.fetch_wsj and args.input_csv:
        parser.error("supply an input CSV or --fetch-wsj, not both")
    if args.months < 1 or args.max_quote_age_days < 0:
        parser.error("--months must be positive and --max-quote-age-days non-negative")
    try:
        if args.input_csv is None:
            prefix = args.output.with_suffix("")
            securities = fetch_treasuries(args.settlement_date, args.months, args.max_quote_age_days,
                                         prefix.with_name(prefix.name + "_source.json"))
            input_path = prefix.with_name(prefix.name + "_input.csv")
            write_input_csv(securities, input_path)
            quote_dates = sorted({security.quote_date for security in securities})
            print(f"Fetched {len(securities)} indicative WSJ quotes dated {', '.join(quote_dates)}; calculation lots assumed $1,000. Broker purchase limits unavailable.")
        else:
            securities = read_treasuries(args.input_csv)
        analyses, excluded = [], []
        for security in securities:
            try:
                analyses.append(analyse_treasury(security, args.settlement_date, args.investment, args.fee))
            except UnaffordableTreasury as error:
                if not args.skip_unaffordable:
                    raise
                excluded.append(dict(cusip=security.cusip, security_id=security.security_id, name=security.name,
                                     minimum_nominal=security.minimum_nominal, reason=str(error)))
        paths = write_reports(analyses, args.output)
        from gilt_analyser.summary import write_summary
        write_summary(ranked_rows(analyses), args.output, treasury=True,
                      source=str(args.input_csv) if args.input_csv else 'Current indicative WSJ quotes (assumed calculation lots)',
                      excluded=excluded, settlement=args.settlement_date, budget=args.investment, fee=args.fee)
        if args.skip_unaffordable:
            excluded_path = args.output.with_suffix("").with_name(args.output.with_suffix("").name + "_excluded.csv")
            with excluded_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("cusip", "security_id", "name", "minimum_nominal", "reason"))
                writer.writeheader()
                writer.writerows(excluded)
            print(f"Analysed {len(analyses)} offers; excluded {len(excluded)} unaffordable offers. Wrote {excluded_path}")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Wrote {paths[0]}, {paths[1]} and {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
