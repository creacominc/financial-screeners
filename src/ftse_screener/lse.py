"""FTSE 350 identities from the public data URL used by LSE's constituent table.

This is a website endpoint, not a contracted market-data API. No price or
execution evidence is inferred from constituent membership.
"""
import json
import re
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.parse import urlparse

SOURCE = 'https://www.londonstockexchange.com/en/indices/ftse-350/constituents'
DATA_URL = 'https://apidata.londonstockexchange.com/instrument-summaries/v1?indexCode=NMX'


def fetch(url):
    if url != DATA_URL:
        raise ValueError('Unsupported LSE constituent URL')
    request = Request(url, headers={'User-Agent': 'financial-screeners/0.1 personal-research'})
    with urlopen(request, timeout=30) as response:
        if urlparse(response.url).hostname != 'apidata.londonstockexchange.com':
            raise ValueError('Unexpected LSE redirect')
        return response.read().decode('utf-8')


def fetch_constituents(get=fetch):
    payload = json.loads(get(DATA_URL), parse_float=Decimal)
    if not isinstance(payload, dict) or payload.get('statusCode') != 200 or not isinstance(payload.get('Data'), list):
        raise ValueError('LSE constituent response missing successful Data array')
    rows = payload['Data']
    if not 300 <= len(rows) <= 400:
        raise ValueError(f'Incomplete/unexpected LSE FTSE universe: {len(rows)} rows')
    result, isins, sedols, tickers = [], set(), set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid LSE constituent row')
        isin, sedol, ticker = row.get('isinCode'), row.get('sedol'), row.get('tidm')
        if (not isinstance(isin, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', isin)
                or not isinstance(sedol, str) or not re.fullmatch(r'[A-Z0-9]{7}', sedol)
                or not isinstance(ticker, str) or not ticker.strip() or not row.get('name')):
            raise ValueError('LSE constituent missing usable ISIN, SEDOL, ticker or name')
        if isin in isins or sedol in sedols or ticker in tickers:
            raise ValueError('Duplicate LSE constituent identity')
        isins.add(isin)
        sedols.add(sedol)
        tickers.add(ticker)
        result.append(dict(isin=isin, sedol=sedol, ticker=ticker, company=row['name'],
                           hl_url='https://www.hl.co.uk/shares/shares-search-results/' + sedol,
                           source=SOURCE))
    return sorted(result, key=lambda row: row['isin'])
