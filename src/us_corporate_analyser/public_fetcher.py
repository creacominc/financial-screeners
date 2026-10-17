"""Public.com discovery snapshots and explicitly hypothetical regular-bond returns.

No account, authentication, broker availability, Moody's clearance or execution
review is inferred. Public's callable flag is not contractual verification.
"""
import argparse
import csv
import html
from html.parser import HTMLParser
import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_DOWN
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from openpyxl import Workbook
from gilt_analyser.calculator import annualised_yield
from gilt_analyser.cli import decimal_argument
from gilt_analyser.models import CashFlow
from .calculator import _coupon_date
from .screening import SP, maturity_limit

BASE_URL = 'https://public.com/bonds/screener'
# Retain source conflicts supplied by the user. Fetching never clears them.
CALL_CONFLICTS = {
    '89115A3A8': 'User-supplied Schwab snapshot says Callable Yes / Make Whole Call; Public says non-callable',
    '05724BAD1': 'User-supplied Schwab snapshot says Callable Yes / Make Whole Call',
}
COLUMNS = ('name', 'months_to_maturity', 'projected_annualised_return_pct', 'rank', 'cusip',
    'review_status', 'sp', 'moodys', 'maturity_date', 'calculation_settlement_date', 'currency',
    'source_price_per_100', 'source_ytw_pct', 'coupon_rate_pct', 'source_next_coupon_date',
    'assumed_accrued_interest_per_100', 'assumed_dirty_price_per_100', 'investment_budget',
    'dealing_fee', 'assumed_nominal_purchased', 'model_clean_consideration', 'model_accrued_interest_paid',
    'model_total_initial_cost', 'model_unused_cash', 'model_coupon_income', 'model_redemption_proceeds',
    'model_redemption_gain', 'model_total_proceeds', 'model_total_cash_profit',
    'assumed_minimum_nominal', 'assumed_nominal_increment', 'source_callable', 'source_sp_creditwatch',
    'source_sp_outlook', 'source_sp_outlook_date', 'quote_timestamp', 'rating_effective_date',
    'fetched_at_utc', 'source_url', 'assumptions')
ASSUMPTIONS = ('RESEARCH ONLY: fixed regular semiannual coupon and bullet par redemption assumed, '
    'not verified; source non-callable flag not independently verified; 30/360 accrual assumed; '
    'USD 1000 calculation minimum/increment assumed; no broker offer size or execution availability; '
    'source quote timestamp and rating effective date unavailable; Moody\'s unavailable. '
    'Conditional on all model payments; no default adjustment; after configured fee, before personal tax.')


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.inside = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def parse_page(document: str, expected_page: int):
    parser = _NextData()
    parser.feed(document)
    try:
        data = json.loads(''.join(parser.parts), parse_float=Decimal)
        collection = data['props']['pageProps']['assetCollection']
        records = collection['content']
        pages, total = collection['totalPages'], collection['totalElements']
        if (not isinstance(records, list) or type(pages) is not int or type(total) is not int
                or pages < 0 or total < 0 or collection['number'] != expected_page
                or collection['numberOfElements'] != len(records)):
            raise ValueError('Invalid page metadata')
        if not all(isinstance(row, dict) for row in records):
            raise ValueError('Invalid bond records')
        return collection
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f'Public screener schema changed or returned an error on page {expected_page}') from error


def download(url):
    request = Request(url, headers={'User-Agent': 'financial-screeners/0.1 (personal bond research)',
                                   'Accept': 'text/html'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(8_000_001).decode('utf-8')
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise ValueError(f'Public screener HTTP {error.code}; no supplied/sample fallback') from error
            time.sleep(attempt + 1)
        except (URLError, TimeoutError) as error:
            raise ValueError(f'Public screener fetch failed: {error}; no supplied/sample fallback') from error


def fetch_records(settlement, months, snapshot_dir, fetch=download, max_pages=50):
    if not 1 <= months <= 24:
        raise ValueError('months must be 1..24')
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    # A failed new fetch must not leave an older success manifest in place.
    (snapshot_dir / 'manifest.json').unlink(missing_ok=True)
    query = {'bondType': 'CORPORATE', 'minMaturityDate': settlement.isoformat(),
             'maxMaturityDate': maturity_limit(settlement, months).isoformat(),
             'callable': 'false', 'partialPar': 'false',
             'sortProperty': 'cusip', 'sortDirection': 'ASC', 'pageSize': 1000}
    records, seen, manifests = [], set(), []
    pages, total = None, None
    page = 0
    while pages is None or page < pages:
        url = BASE_URL + '?' + urlencode({**query, 'pageNumber': page})
        document = fetch(url)
        if len(document) > 8_000_000:
            raise ValueError('Public screener response exceeds size limit')
        collection = parse_page(document, page)
        if pages is None:
            pages, total = collection['totalPages'], collection['totalElements']
            if pages > max_pages or (pages == 0 and total != 0):
                raise ValueError('Unexpected universe size; refusing a truncated result')
        elif (collection['totalPages'], collection['totalElements']) != (pages, total):
            raise ValueError('Public universe changed while paging; retry the run')
        path = snapshot_dir / f'page-{page:03d}.json'
        path.write_text(json.dumps(collection, indent=2, default=str) + '\n')
        manifests.append({'page': page, 'url': url, 'snapshot': path.name})
        for record in collection['content']:
            cusip = record.get('cusip')
            if not isinstance(cusip, str) or len(cusip) != 9 or not cusip.isascii() or not cusip.isalnum() or cusip in seen:
                raise ValueError('Missing/duplicate CUSIP while paging; refusing incomplete results')
            seen.add(cusip)
            records.append(record)
        page += 1
    if len(records) != total:
        raise ValueError('Fetched count differs from advertised total; refusing incomplete results')
    expected_snapshots = {entry['snapshot'] for entry in manifests}
    for stale in snapshot_dir.glob('page-*.json'):
        if stale.name not in expected_snapshots:
            stale.unlink()
    fetched = datetime.now(timezone.utc).isoformat()
    (snapshot_dir / 'manifest.json').write_text(json.dumps(dict(fetched_at_utc=fetched,
        source=BASE_URL, total=total, pages=manifests), indent=2) + '\n')
    return records, fetched


def numeric(record, key, *, positive=False):
    value = record.get(key)
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise ValueError(f'Missing or invalid {key}')
    try:
        result = Decimal(value)
    except ArithmeticError as error:
        raise ValueError(f'Invalid {key}') from error
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError(f'Invalid {key}')
    return result


def project_record(record, settlement, budget, fee, minimum_sp, months, fetched):
    """A hypothetical regular-bond model, never a verified corporate offer."""
    cusip = record['cusip']
    if cusip in CALL_CONFLICTS:
        raise ValueError('Callability conflict: ' + CALL_CONFLICTS[cusip])
    if record.get('bondType') != 'CORPORATE' or record.get('bondStatus') != 'OUTSTANDING':
        raise ValueError('Not an outstanding corporate bond')
    if record.get('callable') is not False or record.get('nextCallDate') or record.get('nextCallPrice'):
        raise ValueError('Callable or missing/conflicting call status')
    if record.get('partialPar') is not False or record.get('perpetual') is not False:
        raise ValueError('Fractional/perpetual or unknown structure')
    if record.get('couponFrequency') != 'SEMI_ANNUAL':
        raise ValueError('Not a semiannual coupon')
    sp = record.get('rating')
    if sp not in SP or SP.index(sp) > SP.index(minimum_sp):
        raise ValueError('S&P rating missing, unknown or below minimum')
    name = record.get('description', '')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Missing description')
    if any(term in name.lower() for term in ('floating', 'variable', 'step', 'convertible', 'structured', 'zero coupon')):
        raise ValueError('Description indicates unsupported coupon/security terms')
    if record.get('currency', 'USD') != 'USD':
        raise ValueError('Not USD')
    maturity = date.fromisoformat(record['maturityDate'])
    if not settlement < maturity <= maturity_limit(settlement, months):
        raise ValueError('Outside requested calendar maturity window')
    # Avoid unsupported February/month-end accrual variants and EOM schedules.
    if maturity.day > 27:
        raise ValueError('Month-end schedule/accrual requires contractual verification')
    coupon = numeric(record, 'coupon', positive=True)
    price = numeric(record, 'currentPrice', positive=True) * 100
    if numeric(record, 'parValue', positive=True) != 1000:
        raise ValueError('Non-standard par value')
    dates, periods = [], 0
    while (day := _coupon_date(maturity, periods)) > settlement:
        dates.append(day)
        periods += 1
    dates.reverse()
    previous = _coupon_date(maturity, periods)
    if date.fromisoformat(record['nextCouponDate']) != dates[0]:
        raise ValueError('Source next coupon differs from regular maturity-anchored schedule')
    if date.fromisoformat(record['issueDate']) > previous:
        raise ValueError('First/irregular accrual period requires verification')
    elapsed = (settlement.year - previous.year)*360 + (settlement.month - previous.month)*30 + settlement.day - previous.day
    accrued = coupon * Decimal(elapsed) / 360
    dirty = price + accrued
    nominal = (((budget-fee)*100/dirty) / 1000).to_integral_value(rounding=ROUND_DOWN) * 1000
    if nominal < 1000:
        raise ValueError('Unaffordable under assumed USD 1000 calculation lot')
    clean = nominal * price / 100
    accrued_paid = nominal * accrued / 100
    initial = clean + accrued_paid + fee
    if initial > budget:
        nominal -= 1000
        if nominal < 1000:
            raise ValueError('Unaffordable after Decimal rounding guard')
        clean, accrued_paid = nominal*price/100, nominal*accrued/100
        initial = clean+accrued_paid+fee
    flows = tuple(CashFlow(day, nominal*coupon/200, nominal if day == maturity else Decimal(0)) for day in dates)
    income = sum((f.coupon for f in flows), Decimal(0))
    projected = annualised_yield(initial, flows, settlement) * 100
    return dict(name=name, months_to_maturity=(Decimal((maturity-settlement).days)*12/365).quantize(Decimal('.01')),
        projected_annualised_return_pct=projected, rank=0, cusip=cusip, review_status='REVIEW - hypothetical terms; not execution-cleared',
        sp=sp, moodys='', maturity_date=maturity, calculation_settlement_date=settlement, currency='USD (source market; assumed)',
        source_price_per_100=price, source_ytw_pct=numeric(record, 'currentYield'), coupon_rate_pct=coupon,
        source_next_coupon_date=record['nextCouponDate'], assumed_accrued_interest_per_100=accrued,
        assumed_dirty_price_per_100=dirty, investment_budget=budget, dealing_fee=fee,
        assumed_nominal_purchased=nominal, model_clean_consideration=clean, model_accrued_interest_paid=accrued_paid,
        model_total_initial_cost=initial, model_unused_cash=budget-initial, model_coupon_income=income,
        model_redemption_proceeds=nominal, model_redemption_gain=nominal-clean, model_total_proceeds=income+nominal,
        model_total_cash_profit=income+nominal-initial, assumed_minimum_nominal=Decimal(1000), assumed_nominal_increment=Decimal(1000),
        source_callable=False, source_sp_creditwatch=record.get('spCreditwatch') or '',
        source_sp_outlook=record.get('spOutlook') or '', source_sp_outlook_date=record.get('spOutlookDate') or '',
        quote_timestamp='', rating_effective_date='', fetched_at_utc=fetched, source_url=BASE_URL,
        assumptions=ASSUMPTIONS)


def screen(records, settlement, budget, fee, minimum_sp, months, fetched):
    if (not isinstance(budget, Decimal) or not budget.is_finite() or budget <= 0
            or not isinstance(fee, Decimal) or not fee.is_finite() or fee < 0 or fee >= budget):
        raise ValueError('Budget must be positive finite Decimal; fee finite, non-negative and less than budget')
    if minimum_sp not in SP[:7] or not 1 <= months <= 24:
        raise ValueError('Public research requires S&P A- or higher and a 1..24 month window')
    rows, excluded = [], []
    for record in records:
        try:
            rows.append(project_record(record, settlement, budget, fee, minimum_sp, months, fetched))
        except (ValueError, ArithmeticError, KeyError, TypeError) as error:
            excluded.append(dict(cusip=record.get('cusip', ''), name=record.get('description', ''), reason=str(error)))
    rows.sort(key=lambda r: (-(r['projected_annualised_return_pct']/Decimal('.1')).to_integral_value(rounding=ROUND_FLOOR),
        (r['maturity_date']-settlement).days, -r['projected_annualised_return_pct'], r['cusip']))
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows, excluded


def write_discovery(rows, excluded, prefix, context):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix, columns, data in [('.csv', COLUMNS, rows), ('_excluded.csv', ('cusip', 'name', 'reason'), excluded)]:
        with Path(str(prefix)+suffix).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data)
    book = Workbook()
    sheet = book.active
    sheet.title = 'Corporate research only'
    sheet.append(list(COLUMNS))
    for row in rows:
        sheet.append([float(row[k]) if isinstance(row[k], Decimal) else row[k] for k in COLUMNS])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    book.save(Path(str(prefix)+'.xlsx'))
    safe = lambda value: html.escape(str(value)).replace('|', '/').replace('\r', ' ').replace('\n', ' ')
    lines = ['# Automatically fetched USD corporate bond research', '', context, '',
        '**Every ranked row is REVIEW, not an execution-cleared selection.**', '',
        ASSUMPTIONS, '', 'Returns below are hypothetical annual effective Actual/365 money-weighted projections, not provider YTM/YTW.',
        'The CSV/XLSX source_ytw_pct column is Public\'s reported yield to worst, mapped from its raw currentYield field; no separate source YTM is supplied.',
        'Public prices are indicative; no quote timestamp, firm offer size or Schwab availability is supplied. Fetch time is not quote time.',
        'Only the Public S&P field is screened (A- or higher). Moody\'s is unavailable and is not inferred.',
        'Known callability conflicts remain excluded. Source fields and model assumptions require broker/prospectus verification.',
        'Ranking: descending 0.1 percentage-point projection band, shorter maturity, precise projection, CUSIP.',
        f'Fetched {len(rows)+len(excluded)} records; {len(rows)} research projections; {len(excluded)} exclusions. Top 50:', '',
        '| Name | Months | Projected annualised return % | S&P | CUSIP |', '|---|---:|---:|---|---|']
    for row in rows[:50]:
        lines.append('| ' + ' | '.join(safe(v) for v in [row['name'], row['months_to_maturity'],
            f"{row['projected_annualised_return_pct']:.4f}", row['sp'], row['cusip']]) + ' |')
    Path(str(prefix)+'.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description='Automatically fetch public corporate bond research; all projections require review')
    parser.add_argument('--settlement-date', type=date.fromisoformat, required=True, help='Explicit model date; not broker-confirmed')
    parser.add_argument('--investment', type=decimal_argument, default=Decimal('5000'))
    parser.add_argument('--fee', type=decimal_argument, default=Decimal('0'))
    parser.add_argument('--months', type=int, default=24)
    parser.add_argument('--minimum-sp', default='A-')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    prefix = args.output or Path(f'reports/us-corporate-research-{args.settlement_date}')
    try:
        # Validate configuration before making any external requests.
        screen([], args.settlement_date, args.investment, args.fee, args.minimum_sp, args.months, '')
        records, fetched = fetch_records(args.settlement_date, args.months, Path(str(prefix)+'_source'))
        rows, excluded = screen(records, args.settlement_date, args.investment, args.fee, args.minimum_sp, args.months, fetched)
        context = (f'Model settlement: {args.settlement_date}; USD budget per bond: {args.investment}; fee: {args.fee}; '
            f'maturity window: {args.months} calendar months; S&P floor: {args.minimum_sp}; fetched at: {fetched}.')
        write_discovery(rows, excluded, prefix, context)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'Fetched {len(records)}; {len(rows)} REVIEW projections; {len(excluded)} exclusions. Wrote {prefix}.*')


if __name__ == '__main__':
    main()
