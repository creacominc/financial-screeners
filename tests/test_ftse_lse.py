"""LSE membership identity and completeness checks; no network calls."""
import json
from pathlib import Path

import pytest

from ftse_screener import lse, hl


def payload(count=350):
    return dict(statusCode=200, Data=[dict(isinCode=f'GB{i:010d}', sedol=f'{i:07d}',
                                         tidm=f'T{i}', name=f'Company {i}')
                                    for i in range(count)])


def test_lse_constituents_preserve_identity_without_inventing_price_evidence():
    urls = []
    def get(url):
        urls.append(url)
        return json.dumps(payload())
    rows = lse.fetch_constituents(get)
    assert urls == [lse.DATA_URL]
    assert len(rows) == 350
    assert rows[0] == dict(isin='GB0000000000', sedol='0000000', ticker='T0',
                          company='Company 0', source=lse.SOURCE,
                          hl_url='https://www.hl.co.uk/shares/shares-search-results/0000000')
    assert 'price' not in rows[0]


@pytest.mark.parametrize('count', [0, 220, 401])
def test_lse_rejects_incomplete_or_unexpected_universe(count):
    with pytest.raises(ValueError, match='Incomplete/unexpected LSE FTSE universe'):
        lse.fetch_constituents(lambda _: json.dumps(payload(count)))


@pytest.mark.parametrize('field', ['isinCode', 'sedol', 'tidm'])
def test_lse_rejects_duplicate_identifiers(field):
    data = payload()
    data['Data'][1][field] = data['Data'][0][field]
    with pytest.raises(ValueError, match='Duplicate LSE constituent identity'):
        lse.fetch_constituents(lambda _: json.dumps(data))


@pytest.mark.parametrize('field', ['isinCode', 'sedol', 'tidm', 'name'])
def test_lse_rejects_missing_identifiers(field):
    data = payload()
    data['Data'][0][field] = None
    with pytest.raises(ValueError, match='LSE constituent missing usable'):
        lse.fetch_constituents(lambda _: json.dumps(data))


@pytest.mark.parametrize('data', [[], {'statusCode': 500, 'Data': []}, {'statusCode': 200}])
def test_lse_rejects_error_envelopes(data):
    with pytest.raises(ValueError, match='missing successful Data array'):
        lse.fetch_constituents(lambda _: json.dumps(data))


@pytest.mark.parametrize('mismatch', [False, True])
def test_lse_refresh_checks_hl_identity_and_preserves_reviews(monkeypatch, mismatch):
    data = json.loads(Path('examples/ftse_snapshot.json').read_text())
    data['illustrative'] = False
    stock = data['stocks'][0]
    url = stock['hl_url'] = 'https://www.hl.co.uk/shares/shares-search-results/TEST'
    review = stock['gate_evidence'].copy()
    monkeypatch.setattr(lse, 'fetch_constituents', lambda _: [dict(hl_url=url, isin=stock['isin'])])
    monkeypatch.setattr(hl, 'discover', lambda *args: pytest.fail('HL universe must not be fetched'))
    parsed = dict(stock, metrics={}, isin='WRONG' if mismatch else stock['isin'])
    monkeypatch.setattr(hl, 'parse_factsheet', lambda *args: parsed)
    if mismatch:
        with pytest.raises(ValueError, match='LSE/HL ISIN mismatch'):
            hl.refresh(data, get=lambda _: '', pause=lambda _: None,
                       discover_universe=True, universe_source='lse')
    else:
        result = hl.refresh(data, get=lambda _: '', pause=lambda _: None,
                            discover_universe=True, universe_source='lse')
        refreshed = next(s for s in result['stocks'] if s['isin'] == stock['isin'])
        assert refreshed['gate_evidence'] == review
        assert refreshed['membership']['source'] == lse.SOURCE
        assert result['refresh']['universe_source'] == lse.SOURCE
        assert result['refresh']['constituent_count'] == 1
