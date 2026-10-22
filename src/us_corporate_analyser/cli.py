from gilt_analyser.trading_dates import default_settlement_date
import argparse
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

from gilt_analyser.cli import decimal_argument
from .calculator import UnaffordableCorporateBond, analyse_bond
from .reporting import read_bonds, write_reports
from .screening import exclusion_reason


def main():
    parser = argparse.ArgumentParser(description='Screen supplied USD corporate bond offers; no automatic inventory feed')
    parser.add_argument('input_csv', type=Path)
    parser.add_argument('--settlement-date', type=date.fromisoformat, default=default_settlement_date('US'), help='YYYY-MM-DD (default: next US trading date)')
    parser.add_argument('--investment', type=decimal_argument, required=True, help='USD budget per bond')
    parser.add_argument('--fee', type=decimal_argument, default=Decimal('0'), help='Total USD fee per purchase; include applicable broker charges')
    parser.add_argument('--months', type=int, default=24)
    parser.add_argument('--minimum-moodys', default='A2')
    parser.add_argument('--minimum-sp', default='A-')
    parser.add_argument('--max-quote-age-days', type=int, default=7)
    parser.add_argument('--max-rating-age-days', type=int, default=90)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    prefix = args.output or Path(f'reports/us-corporate-comparison-{args.settlement_date}')
    try:
        if not args.investment.is_finite() or not args.fee.is_finite() or args.investment <= 0 or args.fee < 0 or args.fee >= args.investment:
            raise ValueError('Budget must be positive; fee must be non-negative and less than budget')
        bonds = read_bonds(args.input_csv)
        analyses, excluded = [], []
        for bond in bonds:
            reason = exclusion_reason(bond, args.settlement_date, args.months, args.minimum_moodys,
                                      args.minimum_sp, args.max_quote_age_days, args.max_rating_age_days)
            if not reason:
                try:
                    analyses.append(analyse_bond(bond, args.settlement_date, args.investment, args.fee))
                except UnaffordableCorporateBond as error:
                    reason = str(error)
            if reason:
                excluded.append(dict(cusip=bond.cusip, name=bond.name, reason=reason))
        context = (f'Settlement: {args.settlement_date}; budget per bond: USD {args.investment}; fee: USD {args.fee}; '
                   f'maturity window: {args.months} calendar months; minimum issue ratings: {args.minimum_moodys} / {args.minimum_sp}; '
                   f'quote age limit: {args.max_quote_age_days} days; ratings age limit: {args.max_rating_age_days} days.')
        write_reports(analyses, excluded, prefix, context)
        snapshot = prefix.with_name(prefix.name + '_input.csv')
        if args.input_csv.resolve() != snapshot.resolve():
            shutil.copyfile(args.input_csv, snapshot)
    except (ValueError, ArithmeticError, OSError) as error:
        parser.error(str(error))
    print(f'{len(analyses)} ranked; {len(excluded)} excluded. Reports: {prefix}.*')


if __name__ == '__main__':
    main()
