import csv
from dataclasses import fields
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

from openpyxl import Workbook

from .calculator import CorporateBond, validate

REQUIRED = ('cusip', 'name', 'coupon_rate', 'maturity_date', 'clean_buy_price',
            'accrued_interest_per_100', 'price_settlement_date', 'moodys', 'sp',
            'ratings_date', 'currency', 'terms', 'minimum_nominal', 'nominal_increment',
            'maximum_nominal', 'quote_date', 'price_source')
DECIMALS = ('coupon_rate', 'clean_buy_price', 'accrued_interest_per_100',
            'minimum_nominal', 'nominal_increment', 'maximum_nominal', 'broker_ytm_pct', 'broker_ytw_pct', 'source_selected_nominal', 'source_accrued_interest', 'source_estimated_total')
COLUMNS = ('name', 'months_to_maturity', 'net_annualised_return_pct', 'rank', 'cusip',
           'moodys', 'sp', 'ratings_date', 'currency', 'maturity_date', 'settlement_date',
           'coupon_rate', 'clean_buy_price', 'accrued_interest_per_100', 'dirty_price_per_100',
           'investment_budget', 'dealing_fee', 'nominal_purchased', 'total_initial_cost',
           'unused_cash', 'coupon_income', 'clean_consideration', 'accrued_interest_paid',
           'redemption_proceeds', 'redemption_gain', 'total_proceeds', 'total_cash_profit',
           'minimum_nominal', 'nominal_increment', 'maximum_nominal', 'broker_ytm_pct',
           'broker_ytw_pct', 'source_selected_nominal', 'source_accrued_interest', 'source_estimated_total',
           'quote_date', 'price_source', 'price_settlement_date', 'terms')


def read_bonds(path: Path) -> list[CorporateBond]:
    result, seen = [], set()
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if set(REQUIRED) - set(reader.fieldnames or ()):
            raise ValueError('Missing required CSV columns: ' + ', '.join(sorted(set(REQUIRED) - set(reader.fieldnames or ()))))
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('Duplicate CSV columns')
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError('Wrong number of CSV cells')
                data = {key: value.strip() for key, value in row.items() if key in {f.name for f in fields(CorporateBond)}}
                for key in DECIMALS:
                    if key in data:
                        data[key] = Decimal(data[key]) if data[key] else None
                data['maturity_date'] = date.fromisoformat(data['maturity_date'])
                bond = CorporateBond(**data)
                validate(bond)
                if bond.cusip in seen:
                    raise ValueError('Duplicate CUSIP')
                seen.add(bond.cusip)
                result.append(bond)
            except (ValueError, ArithmeticError, TypeError, AttributeError) as error:
                raise ValueError(f'CSV line {line}: {error}') from error
    if not result:
        raise ValueError('No input bonds; supply a broker quote export in the documented schema')
    return result


def ranked_rows(analyses):
    ordered = sorted(analyses, key=lambda a: (
        -(a.annualised_yield / Decimal('.001')).to_integral_value(rounding=ROUND_FLOOR),
        (a.bond.maturity_date - a.settlement_date).days, -a.annualised_yield, a.bond.cusip))
    rows = []
    for rank, item in enumerate(ordered, 1):
        row = {key: getattr(item, key, getattr(item.bond, key, '')) for key in COLUMNS}
        row.update(rank=rank, months_to_maturity=(Decimal((item.bond.maturity_date - item.settlement_date).days) * 12 / 365).quantize(Decimal('.01')),
                   net_annualised_return_pct=item.annualised_yield * 100)
        rows.append(row)
    return rows


def write_reports(analyses, excluded, prefix: Path, context: str):
    rows = ranked_rows(analyses)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for path, columns, data in [(prefix.with_suffix('.csv'), COLUMNS, rows),
                                (prefix.with_name(prefix.name + '_excluded.csv'), ('cusip', 'name', 'reason'), excluded)]:
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'USD corporate bonds'
    sheet.append(list(COLUMNS))
    for row in rows:
        values = [float(row[key]) if isinstance(row[key], Decimal) else row[key] for key in COLUMNS]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Broker text is data, never an Excel formula.
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(prefix.with_suffix('.xlsx'))
    def safe(value):
        return str(value).replace('|', '/').replace('\n', ' ').replace('\r', ' ').replace('<', '&lt;').replace('>', '&gt;')
    lines = ['# USD corporate bond comparison', '', context, '',
             'Supplied broker offers; availability is unverified until broker trade preview. All amounts USD.',
             'Annual effective Actual/365 money-weighted return after the configured fee, before personal tax, conditional on all promised payments. Not a default-adjusted return or broker bond-equivalent YTM.',
             'Accrued interest is supplied by the broker for this settlement date. Callable/unknown terms are excluded.',
             'Rank: descending 0.1 percentage-point return band, shorter maturity, precise return, CUSIP.',
             f'{len(rows)} ranked; {len(excluded)} excluded. Top 50 below; full results and exclusions in artifacts.', '',
             '| Name | Months to maturity | Annualised return % | Moody’s / S&P | CUSIP | Quote date |',
             '|---|---:|---:|---|---|---|']
    for row in rows[:50]:
        lines.append('| ' + ' | '.join(safe(x) for x in [row['name'], row['months_to_maturity'], f"{row['net_annualised_return_pct']:.4f}", f"{row['moodys'] or 'NR'} / {row['sp'] or 'NR'}", row['cusip'], row['quote_date']]) + ' |')
    prefix.with_suffix('.md').write_text('\n'.join(lines) + '\n')
