"""Conservative public factsheet adapter; never clears security/PFIC or HL eligibility."""
import argparse
import copy
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

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
    with urlopen(request, timeout=30) as response:
        if urlparse(response.url).hostname != 'www.hl.co.uk':
            raise ValueError('Unexpected HL redirect')
        return response.read().decode('utf-8')


def parse_factsheet(html, url):
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    try:
        payload = json.loads(html.split(marker, 1)[1].split('</script>', 1)[0], parse_float=Decimal)
        props = payload['props']['pageProps']
        detail = props['investmentDetails']
        overview = props['instrumentInfoOverview']
        facts = overview['keyFacts']
        timestamp = datetime.fromisoformat(detail['exchange']['current_timestamp'])
        price = detail['buy']
        if timestamp.tzinfo is None or number(price['value']) <= 0 or price['currency'] not in ('GBP', 'GBX'):
            raise ValueError('Missing usable price/timestamp')
        result = dict(isin=detail['isin'], ticker=detail['epicCode'], company=detail['title'],
                      share_class=detail['description'], sector=facts['sector'], hl_url=url,
                      security_type='unknown',
                      price=dict(value=str(price['value']),currency=price['currency'],
                                 date=timestamp.date().isoformat(),source=url,
                                 timestamp=timestamp.isoformat(),basis='Delayed indicative buy price'), metrics={})
        # "share" is not evidence of an operating company or absence of PFIC risk.
        if detail.get('links', {}).get('investment_trust_details'):
            result['security_type'] = 'investment_trust'
        if detail.get('links', {}).get('etf_details'):
            result['security_type'] = 'etf'
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


def refresh(data, get=fetch, pause=time.sleep, discover_universe=False):
    result = copy.deepcopy(data)
    if data.get('illustrative'):
        raise ValueError('Use a real configuration, not the illustrative snapshot, for HL refresh')
    today = datetime.now(timezone.utc).date().isoformat()
    stocks = {s['isin']:s for s in result['stocks']}
    urls = discover(get, pause) if discover_universe else [s['hl_url'] for s in result['stocks']]
    member_isins = set()
    for url in urls:
        parsed = parse_factsheet(get(url), url)
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
        if parsed['security_type'] in ('investment_trust','etf'):
            old['security_type'] = parsed['security_type']
        old.setdefault('metrics', {}).update(parsed['metrics'])
        if discover_universe:
            old['membership'] = dict(ftse350=True, date=today, source=BASE)
        stocks[isin] = old
        pause(1)
    if discover_universe:
        for isin, stock in stocks.items():
            if isin not in member_isins:
                stock['membership'] = dict(ftse350=False, date=today, source=BASE)
    result['stocks'] = list(stocks.values())
    result['refresh'] = dict(status='HL public fields refreshed; other fields retain original dates',
                             fetched_at_utc=datetime.now(timezone.utc).isoformat(), universe_refreshed=discover_universe)
    return result


def main():
    parser = argparse.ArgumentParser(description='Refresh public HL prices/available fundamentals without login')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--discover-universe', action='store_true', help='fetch all FTSE350 factsheets (one request/second)')
    args = parser.parse_args()
    try:
        result = refresh(json.loads(args.input.read_text(), parse_float=Decimal), discover_universe=args.discover_universe)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, default=str, indent=2)+'\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
