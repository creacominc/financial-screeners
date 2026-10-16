"""Dated, currency-consistent ratios derived from public HL financial statements."""
import json
from datetime import date
from decimal import Decimal

from .engine import number

D = Decimal


def page_props(html):
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    try:
        return json.loads(html.split(marker, 1)[1].split('</script>', 1)[0], parse_float=D)['props']['pageProps']
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError('HL page has no usable financial JSON') from error


def amount(record, field):
    value = record.get(field) or {}
    return number(value['amount']) if value.get('amount') is not None else None


def ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def cagr(first, last, years):
    if first is None or last is None or years <= 0:
        return None
    first, last = number(first), number(last)
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (D(1) / D(years)) - 1) * 100


def compatible(left, right, left_field, right_field):
    a, b = left.get(left_field) or {}, right.get(right_field) or {}
    return bool(a.get('currency')) and a.get('currency') == b.get('currency')


def derive_financials(html, source, observed, expected_isin=None):
    props = page_props(html)
    if expected_isin and props.get('investmentDetails',{}).get('isin') != expected_isin:
        raise ValueError('Financial-statement ISIN does not match share')
    income = sorted((r for r in (props.get('incomeStatement') or {}).get('reported', [])
                     if r.get('period', {}).get('endDate') and not r.get('isProjected')),
                    key=lambda r: r['period']['endDate'])
    cash = {r['period']['endDate']: r for r in (props.get('cashFlow') or {}).get('reported', [])}
    balance = {r['period']['endDate']: r for r in (props.get('balanceSheet') or {}).get('data', [])}
    if not income:
        raise ValueError('No reported annual income statements')
    last = income[-1]
    end = last['period']['endDate']
    if date.fromisoformat(end) > observed:
        raise ValueError('Future reported financial period')
    recent_cash, recent_balance = cash.get(end, {}), balance.get(end, {})
    metrics = {}

    def put(name, value, basis, forecast=False):
        if value is not None:
            metrics[name] = dict(value=str(value), date=observed.isoformat() if forecast else end,
                                 source=source, basis=basis, period_end=end,
                                 observed_date=observed.isoformat())

    margin = amount(last, 'operatingMargin')
    put('operating_margin', margin*100 if margin is not None else None, 'Reported annual operating margin (%)')
    if compatible(recent_cash, last, 'freeCashFlow', 'netIncome'):
        value = ratio(amount(recent_cash, 'freeCashFlow'), amount(last, 'netIncome'))
        put('fcf_conversion', value*100 if value is not None else None, 'Annual FCF / positive net income (%)')
    if compatible(last, recent_balance, 'netIncome', 'totalEquity'):
        value = ratio(amount(last, 'netIncome'), amount(recent_balance, 'totalEquity'))
        put('roe', value*100 if value is not None else None, 'Annual net income / positive closing equity (%); not average-equity ROE')
    if compatible(last, recent_cash, 'operatingIncome', 'depreciation') and compatible(recent_balance, last, 'netDebt', 'operatingIncome'):
        op, dep = amount(last,'operatingIncome'), amount(recent_cash,'depreciation')
        put('net_debt_ebitda', ratio(amount(recent_balance,'netDebt'), op+dep) if op is not None and dep is not None else None,
            'Net debt / (annual operating income + cash-flow depreciation); indicative EBITDA proxy')
    window = income[-5:]
    profits = [amount(r, 'netIncome') for r in window]
    if len(profits) >= 3 and all(v is not None for v in profits):
        put('earnings_consistency', D(sum(v > 0 for v in profits))/D(len(profits))*100,
            f'Positive reported net income in {sum(v > 0 for v in profits)} of {len(profits)} annual periods (%)')
    base = next((r for r in income if r['period']['year'] == last['period']['year']-3), None)
    if base:
        # EPS is reported in the financial statement's reporting currency.
        if compatible(base, last, 'totalRevenue', 'totalRevenue'):
            put('eps_cagr_3y', cagr(amount(base,'dilutedEPS'),amount(last,'dilutedEPS'),3), 'Three-year reported diluted EPS CAGR (%)')
            put('revenue_cagr_3y', cagr(amount(base,'totalRevenue'),amount(last,'totalRevenue'),3), 'Three-year reported revenue CAGR (%); not organic/constant currency')
            put('income_cagr_3y', cagr(amount(base,'netIncome'),amount(last,'netIncome'),3), 'Three-year net income CAGR (%)')
        base_cash = cash.get(base['period']['endDate'], {})
        if compatible(base_cash, recent_cash, 'freeCashFlow', 'freeCashFlow'):
            put('fcf_cagr_3y', cagr(amount(base_cash,'freeCashFlow'),amount(recent_cash,'freeCashFlow'),3), 'Three-year reported FCF CAGR (%)')
    earnings = props.get('earnings') or []
    actual = next((e for e in earnings if not e.get('isProjected') and e.get('year') == last['period']['year']), None)
    forecast = next((e for e in earnings if e.get('isProjected') and e.get('year') == last['period']['year']+1), None)
    if actual and forecast:
        a, f = actual.get('reported') or {}, forecast.get('reported') or {}
        if a.get('currency') and a.get('currency') == f.get('currency'):
            put('forecast_eps_growth', cagr(a.get('amount'),f.get('amount'),1),
                f'HL projected EPS for {forecast["year"]} versus latest reported EPS; forecast observed {observed}', True)
    return metrics


def financial_url(html):
    """Follow the page's actual public link; legacy SEDOL URLs don't accept tab suffixes."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlparse

    class Links(HTMLParser):
        found = None

        def handle_starttag(self, tag, attrs):
            href = dict(attrs).get('href','')
            if tag == 'a' and href.endswith('/financial-statements-and-reports'):
                candidate = urljoin('https://www.hl.co.uk',href)
                if urlparse(candidate).hostname == 'www.hl.co.uk':
                    self.found = candidate
    parser = Links()
    parser.feed(html)
    return parser.found
