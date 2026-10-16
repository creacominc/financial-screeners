"""Conservative public factsheet adapter; never clears security/PFIC or HL eligibility."""
import argparse
import copy
import json
import time
import hashlib
from datetime import datetime, timezone, date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .engine import number

BASE = 'https://www.hl.co.uk/shares/stock-market-summary/ftse-350'


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.pages = set()

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        if tag == 'a':
            url = urljoin(BASE, href)
            parsed = urlparse(url)
            if parsed.hostname != 'www.hl.co.uk':
                return
            if parsed.path.startswith('/shares/shares-search-results/'):
                self.links.add(url)
            elif parsed.path == urlparse(BASE).path and parsed.query.startswith('page='):
                if parsed.query[5:].isdigit():
                    self.pages.add(url)


def fetch(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'www.hl.co.uk':
        raise ValueError('Only public HTTPS HL pages are supported')
    request = Request(url, headers={'User-Agent': 'financial-screeners/0.1 personal-research'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                if urlparse(response.url).hostname != 'www.hl.co.uk':
                    raise ValueError('Unexpected HL redirect')
                return response.read().decode('utf-8')
        except HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt+1))


def parse_factsheet(html, url):
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    try:
        payload = json.loads(html.split(marker, 1)[1].split('</script>', 1)[0], parse_float=Decimal)
        props = payload['props']['pageProps']
        detail = props['investmentDetails']
        overview = props['instrumentInfoOverview']
        facts = overview['keyFacts']
        timestamp = datetime.fromisoformat(detail['exchange']['current_timestamp'])
        price = detail.get('buy') or {}
        if timestamp.tzinfo is None:
            raise ValueError('Missing usable quote timestamp')
        result = dict(isin=detail['isin'], ticker=detail['epicCode'], company=detail['title'],
                      share_class=detail.get('description') or 'Unverified share class', sector=facts.get('sector') or 'Unclassified', hl_url=url,
                      security_type='unknown',
                      industry=facts.get('industry') or '', business_summary=overview.get('businessSummary') or '',
                      hl_account_products=detail.get('applicableProducts',[]),
                      internet_tradable=detail.get('internetTradable'),
                      price=dict(value=str(price['value']) if price.get('value') is not None else None,currency=price.get('currency'),
                                 date=timestamp.date().isoformat(),source=url,
                                 timestamp=timestamp.isoformat(),basis='Delayed indicative buy price'), metrics={})
        # "share" is not evidence of an operating company or absence of PFIC risk.
        if detail.get('links', {}).get('investment_trust_details'):
            result['security_type'] = 'investment_trust'
        if detail.get('links', {}).get('etf_details'):
            result['security_type'] = 'etf'
        if result['security_type'] == 'unknown' and ('real estate' in (facts.get('industry') or '').lower() or 'reit' in (detail.get('title') or '').lower()):
            result['security_type'] = 'reit'
        if result['security_type'] == 'unknown' and any(w in (detail.get('title') or '').lower() for w in ('investment trust', 'income trust', 'capital gearing', 'cash shell')):
            result['security_type'] = 'investment_trust'
        pe = overview.get('keyMetrics', {}).get('pERatio')
        if pe is not None:
            result['metrics']['pe'] = dict(value=str(number(pe)),date=timestamp.date().isoformat(),source=url,
                                           basis='HL displayed P/E; observation date')
        financials = props.get('earningsAndFinancials') or {}
        for section, field, name, scale in [('incomeStatement','operatingMargin','operating_margin',Decimal(100)),
                                          ('cashFlow','freeCashFlow','free_cash_flow',Decimal(1))]:
            block = financials.get(section) or {}
            metric = block.get(field)
            if metric and metric.get('amount') is not None:
                result['metrics'][name] = dict(value=str(number(metric['amount'])*scale),
                    date=block['period']['endDate'],source=url,basis='Reported period end',currency=metric.get('currency'))
        return result
    except (KeyError, IndexError, TypeError, ArithmeticError) as error:
        raise ValueError('HL factsheet missing expected identity, date or financial data') from error


def discover(get=fetch, pause=time.sleep):
    pending, visited, links = {BASE}, set(), set()
    while pending:
        url = min(pending)
        pending.remove(url)
        if url in visited:
            continue
        if len(visited) >= 10:
            raise ValueError('Unexpected HL pagination')
        parser = ListingParser()
        parser.feed(get(url))
        visited.add(url)
        links.update(parser.links)
        pending.update(parser.pages-visited)
        pause(1)
    if not 300 <= len(links) <= 400:
        raise ValueError(f'Incomplete/unexpected FTSE universe: {len(links)} links')
    return sorted(links)


def refresh(data, get=fetch, pause=time.sleep, discover_universe=False, full_metrics=False):
    result = copy.deepcopy(data)
    if data.get('illustrative'):
        raise ValueError('Use a real configuration, not the illustrative snapshot, for HL refresh')
    observed = datetime.now(timezone.utc).date()
    today = observed.isoformat()
    from .fundamentals import derive_financials, financial_url
    from .performance import fetch_performance
    from .policy import populate_policy
    from .evidence import apply_reviews
    performance = fetch_performance(get,pause,observed) if full_metrics else {}
    if full_metrics:
        from .execution import parse_terms, next_cutoff, fetch_holidays, TERMS_URL
        try:
            result['hl_monthly_terms'] = parse_terms(get(TERMS_URL),observed)
            result['hl_cutoff'] = next_cutoff(observed,result['hl_monthly_terms'],fetch_holidays())
            result.pop('execution_error',None)
        except (ValueError, OSError, KeyError, TypeError) as error:
            result.pop('hl_monthly_terms',None)
            result.pop('hl_cutoff',None)
            result['execution_error'] = str(error)
    failures = []
    stocks = {s['isin']:s for s in result['stocks']}
    urls = discover(get, pause) if discover_universe else [s['hl_url'] for s in result['stocks']]
    member_isins = set()
    for index, url in enumerate(urls, 1):
        html = get(url)
        parsed = parse_factsheet(html, url)
        if full_metrics:
            parsed['metrics'].update(performance.get(parsed['ticker'],{}))
            if parsed['security_type'] not in ('investment_trust','etf'):
                financial = financial_url(html)
                try:
                    if not financial:
                        raise ValueError('No public financial statements link')
                    parsed['metrics'].update(derive_financials(get(financial),financial,observed,parsed['isin']))
                    pause(1)
                except (ValueError, OSError, ArithmeticError, KeyError, TypeError) as error:
                    failures.append(dict(ticker=parsed['ticker'],source=financial or url,error=str(error)))
            if index % 25 == 0:
                print(f'Fetched {index}/{len(urls)} FTSE factsheets; {len(failures)} financial-data gaps',flush=True)
        isin = parsed['isin']
        member_isins.add(isin)
        old = stocks.get(isin, {})
        if not discover_universe and not any(s['isin'] == isin and s['hl_url'] == url for s in result['stocks']):
            raise ValueError('HL ISIN changed; manual corporate-event review required')
        if any(old.get(key) and old[key] != parsed[key] for key in ('sector', 'share_class', 'ticker')):
            old['gate_evidence'] = dict(decision='REVIEW', rationale='HL classification/identity changed; review corporate event and policy')
            old['execution'] = dict(eligible=None, source=url, date=today, rationale='Identity/classification changed; reverify exact share class')
        # Supplied review decisions and holding/execution context survive price refresh.
        old.update({k:v for k,v in parsed.items() if k not in ('security_type','metrics')})
        old.setdefault('security_type', parsed['security_type'])
        if parsed['security_type'] in ('investment_trust','etf','reit'):
            old['security_type'] = parsed['security_type']
        old.setdefault('metrics', {}).update(parsed['metrics'])
        old['data_warnings'] = [f['error'] for f in failures if f['ticker'] == parsed['ticker']]
        if discover_universe:
            old['membership'] = dict(ftse350=True, date=today, source=BASE)
        stocks[isin] = old
        pause(1)
    if discover_universe:
        for isin, stock in stocks.items():
            if isin not in member_isins:
                stock['membership'] = dict(ftse350=False, date=today, source=BASE)
    result['stocks'] = list(stocks.values())
    populate_policy(result)
    apply_reviews(result)
    from .portfolio import apply_holdings
    apply_holdings(result)
    result['refresh'] = dict(status='LIVE HL public fields refreshed; gate reviews retain original review dates',
                             financial_data_gaps=failures, constituent_count=len(member_isins),
                             performance_count=len(performance), full_metrics=full_metrics,
                             fetched_at_utc=datetime.now(timezone.utc).isoformat(), universe_refreshed=discover_universe)
    if hasattr(get,'cache_stats'):
        result['refresh']['hl_page_cache'] = dict(get.cache_stats)
    return result



def cached_fetch(directory, pause=None):
    """Cache only within the current UTC date; published metric dates remain unchanged."""
    pause = pause or time.sleep
    root = directory / datetime.now(timezone.utc).date().isoformat()
    root.mkdir(parents=True, exist_ok=True)
    stats = dict(cached_pages=0,downloaded_pages=0,cache_utc_date=root.name)

    def get(url):
        path = root / (hashlib.sha256(url.encode()).hexdigest()+'.html')
        if path.exists():
            stats['cached_pages'] += 1
            return path.read_text(encoding='utf-8')
        html = fetch(url)
        stats['downloaded_pages'] += 1
        pause(1)
        path.write_text(html,encoding='utf-8')
        return html
    get.cache_stats = stats
    return get


def main():
    parser = argparse.ArgumentParser(description='Refresh public HL prices/available fundamentals without login')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--full-metrics', action='store_true', help='include public financial history, forecasts and price-return table')
    parser.add_argument('--cache-dir', type=Path, help='optional same-day public HTML cache')
    parser.add_argument('--discover-universe', action='store_true', help='fetch all FTSE350 factsheets (one request/second)')
    args = parser.parse_args()
    try:
        get = cached_fetch(args.cache_dir) if args.cache_dir else fetch
        result = refresh(json.loads(args.input.read_text(), parse_float=Decimal), get=get, pause=(lambda seconds: None) if args.cache_dir else time.sleep, discover_universe=args.discover_universe, full_metrics=args.full_metrics)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, default=str, indent=2)+'\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
