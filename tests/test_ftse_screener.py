import copy
import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from ftse_screener.engine import screen, component, number
from ftse_screener.cli import write_reports

TODAY = date(2026, 10, 16)


@pytest.fixture
def data():
    data = json.loads(Path('examples/ftse_snapshot.json').read_text())
    data['illustrative'] = False
    stock = data['stocks'][0]
    stock['gate_evidence'].update(decision='PASS', reviewer='Test reviewer', recheck_date='2027-01-01')
    stock['execution'] = dict(date='2026-10-16', source='fixture', account='ISA', eligible=True,
                              contribution_gbp='100', fee_gbp='1.50', purchase_tax_rate='0.005',
                              minimum_gbp='25', cutoff='2026-11-05T17:00:00+00:00')
    return data


def test_weights_affordability_and_rank(data):
    row = screen(data, TODAY)[0]
    assert row['gate_status'] == 'PASS'
    assert row['rank'] == 1
    assert row['estimated_shares'] == 7
    assert row['residual_gbp'] == D('11.68')
    assert row['actionable']
    assert row['components']['diversification'] == 0
    assert row['total_score'] == (D(20)/30*100*D('.30') + D(18)/30*100*D('.25') + D(22)/35*100*D('.20') + D('62.5')*D('.15'))
    assert row['report_due'] == '2026-10-31T17:00:00+00:00'


@pytest.mark.parametrize('kind', ['investment_trust','etf','fund','vct','closed_end_fund','spac','cash_shell'])
def test_prohibited_never_scored(data, kind):
    data['stocks'][0]['security_type'] = kind
    row = screen(data, TODAY)[0]
    assert row['gate_status'] == 'EXCLUDE'
    assert row['total_score'] is None
    assert not row['actionable']


@pytest.mark.parametrize('change', [dict(decision='REVIEW'),dict(date='2020-01-01'),dict(year=2024),dict(conflict=True),dict(recheck_date='2026-10-16'),dict(reviewer=''),dict(source=''),dict(date='2026-10-17')])
def test_unresolved_gate(data, change):
    data['stocks'][0]['gate_evidence'].update(change)
    row = screen(data, TODAY)[0]
    assert row['gate_status'] == 'REVIEW'
    assert row['rank'] is None
    assert row['total_score'] is None


def test_property_review(data):
    data['stocks'][0]['security_type'] = 'reit'
    assert screen(data, TODAY)[0]['gate_status'] == 'REVIEW'


@pytest.mark.parametrize('change', [dict(value=None),dict(value='-1'),dict(date='2020-01-01')])
def test_missing_negative_or_stale_pe_withholds(data, change):
    data['stocks'][0]['metrics']['pe'].update(change)
    assert screen(data, TODAY)[0]['total_score'] is None


def test_sector_policy_required(data):
    data['policy']['sector_metrics'] = {}
    assert screen(data, TODAY)[0]['total_score'] is None


def test_same_rules_for_holdings_and_new_candidates(data):
    second = copy.deepcopy(data['stocks'][0])
    second.update(isin='DEMO00000002', holding=False, prior_rank=5)
    data['stocks'].append(second)
    rows = screen(data, TODAY)
    assert rows[0]['total_score'] == rows[1]['total_score']
    assert [r['rank'] for r in rows] == [1, 2]
    assert rows[1]['rank_change'] == 3


def test_outside_membership_can_compare_but_not_rank(data):
    data['stocks'][0]['membership']['date'] = '2020-01-01'
    row = screen(data, TODAY)[0]
    assert row['total_score'] is not None
    assert row['rank'] is None
    assert not row['actionable']


def test_counts_fallback(data):
    del data['stocks'][0]['holding_value_gbp']
    assert screen(data, TODAY)[0]['portfolio_basis'] == 'holding counts fallback'


@pytest.mark.parametrize('change,status', [(dict(eligible=False),'INELIGIBLE'),(dict(date='2020-01-01'),'UNVERIFIED'),(dict(contribution_gbp='1'),'BLOCKED'),(dict(cutoff='2026-10-01T17:00:00+01:00'),'BLOCKED')])
def test_execution_blocks(data, change, status):
    data['stocks'][0]['execution'].update(change)
    row = screen(data, TODAY)[0]
    assert row['dca_status'] == status
    assert not row['actionable']


def test_round_purchase_cost_up(data):
    data['stocks'][0]['price'].update(value='1', currency='GBP')
    data['stocks'][0]['execution'].update(contribution_gbp='25', fee_gbp='0', purchase_tax_rate='0.005')
    row = screen(data, TODAY)[0]
    assert row['estimated_shares'] == 24
    assert row['residual_gbp'] == D('.88')


@pytest.mark.parametrize('bad', ['NaN','Infinity',0.1,True])
def test_reject_unsafe_numbers(bad):
    with pytest.raises(ValueError):
        number(bad)


def test_duplicates(data):
    data['stocks'].append(copy.deepcopy(data['stocks'][0]))
    with pytest.raises(ValueError, match='duplicate'):
        screen(data, TODAY)


def test_outlier_clamping(data):
    stock = data['stocks'][0]
    stock['metrics']['roic']['value'] = '100000'
    spec = data['policy']['sector_metrics'][stock['sector']]['quality']
    assert component(stock, spec, TODAY, 120)[0] == 100


def test_reports(data, tmp_path):
    rows = screen(data, TODAY)
    prefix = tmp_path/'report'
    write_reports(rows, prefix, TODAY, True)
    parsed = json.loads(prefix.with_suffix('.json').read_text())
    assert parsed['illustrative'] is True
    assert parsed['rows'][0]['estimated_shares'] == '7'
    assert 'REVIEW queue' in prefix.with_suffix('.md').read_text()
    assert 'gate_evidence' in prefix.with_suffix('.csv').read_text()


def test_monthly_report_schedule_uses_london(data):
    from datetime import datetime
    from ftse_screener.automation import report_reason
    assert report_reason(data, datetime.fromisoformat('2026-10-31T07:15:00+00:00')) == 'monthly cutoff review'
    assert report_reason(data, datetime.fromisoformat('2026-10-19T07:15:00+00:00')) == 'weekly'
    assert report_reason(data, datetime.fromisoformat('2026-10-20T07:15:00+00:00')) is None


def factsheet():
    payload = dict(props=dict(pageProps=dict(
        investmentDetails=dict(isin='DEMO00000001', epicCode='DEMO',title='Demo',description='Ordinary',
            exchange=dict(current_timestamp='2026-10-16T08:30:00+01:00'),buy=dict(value='1234.56',currency='GBX'),links={}),
        instrumentInfoOverview=dict(keyFacts=dict(sector='Illustrative sector'), keyMetrics=dict(pERatio='18.5')))))
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(payload)+'</script>'


def test_hl_parser_and_refresh_preserve_evidence(data):
    from ftse_screener.hl import parse_factsheet, refresh
    parsed = parse_factsheet(factsheet(), 'https://www.hl.co.uk/shares/shares-search-results/DEMO')
    assert parsed['price']['value'] == '1234.56'
    assert parsed['security_type'] == 'unknown'
    assert parsed['metrics']['pe']['value'] == '18.5'
    data['illustrative'] = False
    data['stocks'][0]['hl_url'] = parsed['hl_url']
    refreshed = refresh(data, get=lambda url: factsheet(), pause=lambda seconds: None)
    assert refreshed['stocks'][0]['gate_evidence'] == data['stocks'][0]['gate_evidence']
    assert refreshed['stocks'][0]['execution'] == data['stocks'][0]['execution']
    assert refreshed['stocks'][0]['metrics']['pe']['value'] == '18.5'
    assert data['stocks'][0]['metrics']['pe']['value'] == '18'


def test_hl_fails_closed(data):
    from ftse_screener.hl import parse_factsheet, refresh, discover
    with pytest.raises(ValueError):
        parse_factsheet('<html>unavailable</html>', 'url')
    data['illustrative'] = True
    with pytest.raises(ValueError, match='illustrative'):
        refresh(data)
    with pytest.raises(ValueError, match='universe'):
        discover(get=lambda url: '<html>blocked</html>',pause=lambda seconds: None)


def test_illustrative_cannot_be_actionable(data):
    data['illustrative'] = True
    assert not screen(data, TODAY)[0]['actionable']


def test_hl_identity_change_invalidates_reviews(data):
    from ftse_screener.hl import refresh
    data['stocks'][0]['hl_url'] = 'https://www.hl.co.uk/shares/shares-search-results/DEMO'
    data['stocks'][0]['share_class'] = 'Old class'
    result = refresh(data, get=lambda url: factsheet(), pause=lambda seconds: None)
    assert result['stocks'][0]['gate_evidence']['decision'] == 'REVIEW'
    assert result['stocks'][0]['execution']['eligible'] is None


@pytest.mark.parametrize('value', ['-1', '0', '1.1'])
def test_invalid_coverage_policy(data, value):
    data['policy']['minimum_coverage'] = value
    with pytest.raises(ValueError, match='coverage'):
        screen(data, TODAY)


def test_missing_portfolio_withholds_total(data):
    data['stocks'][0]['holding'] = False
    assert screen(data, TODAY)[0]['total_score'] is None


def test_cutoff_date_is_blocked(data):
    data['stocks'][0]['execution']['cutoff'] = '2026-10-16T17:00:00+01:00'
    assert screen(data, TODAY)[0]['dca_status'] == 'BLOCKED'


def test_hl_pagination_parser():
    from ftse_screener.hl import ListingParser
    parser = ListingParser()
    parser.feed('<a href="?page=2">2</a><a href="/shares/shares-search-results/DEMO">Demo</a><a href="https://other.example/shares/shares-search-results/BAD">bad</a>')
    assert len(parser.links) == 1
    assert parser.pages == {'https://www.hl.co.uk/shares/stock-market-summary/ftse-350?page=2'}
