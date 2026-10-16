"""Focused financial and workflow behavior tests use synthetic data, not live quotes."""
import copy
import json
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from ftse_screener.fundamentals import cagr, derive_financials, financial_url
from ftse_screener.execution import next_cutoff, parse_terms, account_scenarios
from ftse_screener.performance import parse_performance
from ftse_screener.policy import populate_policy
from ftse_screener.evidence import apply_reviews
from ftse_screener.engine import screen
from ftse_screener.cli import analyse, write_reports

TODAY=date(2026,10,16)


def wrapped(props):
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(dict(props=dict(pageProps=props)))+'</script>'


def money(value, currency='GBP'):
    return dict(amount=str(value),currency=currency)


def financials():
    income=[]
    cash=[]
    balance=[]
    for year,scale in [(2022,D('1')),(2023,D('1.1')),(2024,D('1.21')),(2025,D('1.331'))]:
        period=dict(year=year,endDate=f'{year}-12-31')
        income.append(dict(period=period,totalRevenue=money(1000*scale), netIncome=money(100*scale),
                           operatingIncome=money(150*scale),operatingMargin=money('.15'),dilutedEPS=money(scale)))
        cash.append(dict(period=period,freeCashFlow=money(120*scale),depreciation=money(50*scale)))
        balance.append(dict(period=period,totalEquity=money(500*scale),netDebt=money(400*scale)))
    return dict(investmentDetails=dict(isin='TEST'),incomeStatement=dict(reported=income),
                cashFlow=dict(reported=cash),balanceSheet=dict(data=balance),
                earnings=[dict(year=2025,isProjected=False,reported=money('1.331')),
                          dict(year=2026,isProjected=True,reported=money('1.4641'))])


def test_derived_financial_formulas():
    m=derive_financials(wrapped(financials()),'source',TODAY,'TEST')
    for name in ['eps_cagr_3y','revenue_cagr_3y','fcf_cagr_3y','income_cagr_3y','forecast_eps_growth']:
        assert abs(D(m[name]['value'])-10)<D('1e-20')
    assert D(m['roe']['value'])==20
    assert D(m['fcf_conversion']['value'])==120
    assert D(m['operating_margin']['value'])==15
    assert D(m['net_debt_ebitda']['value'])==2
    assert D(m['earnings_consistency']['value'])==100
    assert m['roe']['date']=='2025-12-31'
    assert m['forecast_eps_growth']['date']=='2026-10-16'


@pytest.mark.parametrize('first,last', [(0,1),(-1,1),(1,-1),(None,1)])
def test_cagr_rejects_nonpositive_or_missing_base(first,last):
    assert cagr(first,last,3) is None


def test_cagr_integer_inputs_use_decimal():
    assert abs(cagr(1000,1331,3)-10)<D('1e-20')
    assert isinstance(cagr(100,200,1),D)


def test_currency_mismatch_and_missing_forecast_withheld():
    props=financials()
    props['cashFlow']['reported'][-1]['freeCashFlow']['currency']='USD'
    props['earnings'][-1]['reported']['currency']='USD'
    metrics=derive_financials(wrapped(props),'source',TODAY)
    assert 'fcf_conversion' not in metrics
    assert 'fcf_cagr_3y' not in metrics
    assert 'forecast_eps_growth' not in metrics


def test_identity_mismatch_never_uses_other_financials():
    with pytest.raises(ValueError,match='ISIN'):
        derive_financials(wrapped(financials()),'source',TODAY,'OTHER')


def test_follow_financial_link_not_legacy_suffix():
    assert financial_url('<a href="/shares/shares-search-results/d/demo/financial-statements-and-reports">Financials</a>')=='https://www.hl.co.uk/shares/shares-search-results/d/demo/financial-statements-and-reports'
    assert financial_url('<a href="https://evil.example/financial-statements-and-reports">bad</a>') is None


def test_performance_columns_missing_and_corporate_action_guard():
    html='<tr>'+''.join(f'<td>{v}</td>' for v in ['TEST','Test','1','2','3','4','10','15','n/a','50'])+'</tr>'
    result,_=parse_performance(html,'source',TODAY)
    assert result['TEST']['price_return_1y']['value']=='10'
    assert result['TEST']['price_return_5y']['value']=='50'
    assert 'price_return_3y' not in result['TEST']
    result,_=parse_performance(html.replace('<td>10</td>','<td>-99</td>'),'source',TODAY)
    assert 'price_return_1y' not in result['TEST']


TERMS="""FTSE-350 shares. There's no charge to invest by Direct Debit.
The minimum amount is £25 per investment, per month. Changes made fewer than 7 working days before the Direct Debit is taken apply next month.
Direct Debits are taken from your bank account on the 7th of month."""
HOLIDAYS={'england-and-wales':{'events':[{'date':d} for d in ['2026-01-01','2026-12-25','2026-12-28','2027-01-01','2027-12-27']]}}


def test_current_terms_parser_and_change_detection():
    terms=parse_terms(TERMS,TODAY)
    assert terms['minimum_gbp']=='25'
    assert terms['fee_gbp']=='0'
    assert terms['cutoff_working_days']==7
    with pytest.raises(ValueError,match='terms changed'):
        parse_terms(TERMS.replace('no charge to invest','a charge to invest'),TODAY)


def test_next_cutoff_weekends_holidays_and_london_timezone():
    terms=parse_terms(TERMS,TODAY)
    # 7 November 2026 is Saturday: collection Monday 9th; seven prior working days = 29 October.
    assert next_cutoff(TODAY,terms,HOLIDAYS)=='2026-10-29T00:00:00+00:00'
    # 7 January 2027: previous working days exclude New Year and both Christmas holidays.
    assert next_cutoff(date(2026,12,1),terms,HOLIDAYS)=='2026-12-24T00:00:00+00:00'
    with pytest.raises(ValueError,match='calendar'):
        next_cutoff(TODAY,terms,{'england-and-wales':{'events':[]}})


def test_selection_rank_without_fabricating_portfolio_score():
    data=json.loads(Path('examples/ftse_snapshot.json').read_text())
    data['illustrative']=False
    s=data['stocks'][0]
    s['holding']=False
    s['gate_evidence'].update(decision='PASS',reviewer='Reviewer',recheck_date='2027-01-01')
    row=screen(data,TODAY)[0]
    assert row['selection_rank']==1
    assert row['selection_score'] is not None
    assert row['total_score'] is None
    assert row['rank'] is None
    assert not row['actionable']
    s['gate_evidence']['decision']='REVIEW'
    row=screen(data,TODAY)[0]
    assert row['selection_score'] is None
    assert row['selection_rank'] is None


def test_baseline_bank_substitutions():
    data=dict(policy=dict(baseline_policy='hl-public-v1'),stocks=[dict(sector='Financials',industry='Banks')])
    populate_policy(data)
    quality=data['policy']['sector_metrics']['Financials']['quality']
    assert {m['name'] for m in quality}=={'roe','earnings_consistency'}


def test_reviews_exact_identity_and_no_renewal():
    data=json.loads(Path('config/ftse_live.json').read_text())
    data['stocks']=[dict(isin='GB0009895292',ticker='AZN',security_type='unknown')]
    apply_reviews(data)
    assert data['stocks'][0]['gate_evidence']['date']=='2026-10-16'
    data['stocks'][0]['gate_evidence']['decision']='REVIEW'
    apply_reviews(data)
    assert data['stocks'][0]['gate_evidence']['decision']=='REVIEW'


def test_both_account_affordability_and_ownership_context():
    data=json.loads(Path('config/ftse_live.json').read_text())
    data['monthly_per_share_gbp']='100'
    stock=dict(isin='GB0009895292',hl_url='source',internet_tradable=True,hl_account_products=[22,98],
               membership=dict(ftse350=True),security_type='operating_company',positions=[dict(account='Stocks and Shares ISA')],
               price=dict(value='1000',currency='GBX',date='2026-10-16',source='source'))
    rows=account_scenarios(stock,data,TODAY,parse_terms(TERMS,TODAY),'2026-10-29T00:00:00+00:00')
    assert len(rows)==2
    assert all(r['estimated_shares']==9 and r['residual_gbp']==D('9.55') for r in rows)
    assert rows[0]['proposed_action']=='Consider increasing monthly purchase'
    assert rows[1]['proposed_action'].startswith('Confirm ownership')
    assert all(r['minimum_for_one_share_gbp']==25 for r in rows)


def test_workflow_defaults_to_real_data():
    workflow=Path('.github/workflows/run-ftse-screening.yml').read_text()
    assert 'default: config/ftse_live.json' in workflow
    assert '--full-metrics' in workflow
    assert '  push:' in workflow


def test_nullable_hl_industry_does_not_abort_universe():
    from ftse_screener.hl import parse_factsheet
    props=dict(investmentDetails=dict(isin='TEST',epicCode='TEST',title='Test',description='Ordinary',
        exchange=dict(current_timestamp='2026-10-16T08:00:00+01:00'),buy=dict(value=100,currency='GBX'),links={}),
        instrumentInfoOverview=dict(keyFacts=dict(sector=None,industry=None),keyMetrics={}))
    parsed=parse_factsheet(wrapped(props),'source')
    assert parsed['sector']=='Unclassified'
    assert parsed['industry']==''
    assert parsed['security_type']=='unknown'


def test_actual_hl_financial_sector_label_uses_financial_policy():
    data=dict(policy=dict(baseline_policy='hl-public-v1'),stocks=[dict(sector='Financial',industry='Investment Services'),dict(sector='Financial',industry='Regional Banks')])
    populate_policy(data)
    assert {m['name'] for m in data['policy']['sector_metrics']['Financial']['quality']}=={'roe','earnings_consistency'}


def test_unresolved_holdings_withhold_portfolio_context():
    from ftse_screener.portfolio import apply_holdings
    data=dict(stocks=[dict(isin='PRESENT')],holdings=[dict(isin='OTHER',account='Stocks and Shares ISA',value_gbp='1000')])
    apply_holdings(data)
    assert data['unresolved_holdings'][0]['gate_status']=='REVIEW'


def test_live_report_labels_sources_and_selection_rows(tmp_path):
    data=json.loads(Path('examples/ftse_snapshot.json').read_text())
    data['illustrative']=False
    data['stocks'][0]['holding']=False
    data['stocks'][0]['gate_evidence'].update(decision='PASS',reviewer='Reviewer',recheck_date='2027-01-01')
    data['refresh']=dict(full_metrics=True,fetched_at_utc='2026-10-16T09:00:00+00:00')
    rows=analyse(data,TODAY)
    write_reports(rows,tmp_path/'live',TODAY,False,data)
    report=(tmp_path/'live.md').read_text()
    assert 'REAL HL DATA SNAPSHOT' in report
    assert 'Stock-selection shortlist' in report
    assert 'not a claim that unresolved companies are worse' in report
    import csv
    with (tmp_path/'live.csv').open() as handle:
        row=next(csv.DictReader(handle))
    assert row['selection_rank']=='1'
    assert row['pe']=='18'
    assert row['price_gbp']=='12.34'


def test_transient_fetch_failure_retries_without_fixture_fallback(monkeypatch):
    from ftse_screener import hl
    from urllib.error import HTTPError
    calls=[]
    class Response:
        url='https://www.hl.co.uk/shares/test'
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b'real response'
    def open_page(*args,**kwargs):
        calls.append(1)
        if len(calls)==1: raise HTTPError(Response.url,503,'Unavailable',None,None)
        return Response()
    monkeypatch.setattr(hl,'urlopen',open_page)
    monkeypatch.setattr(hl.time,'sleep',lambda seconds:None)
    assert hl.fetch(Response.url)=='real response'
    assert len(calls)==2


def test_permanent_fetch_failure_is_not_retried(monkeypatch):
    from ftse_screener import hl
    from urllib.error import HTTPError
    calls=[]
    def open_page(*args,**kwargs):
        calls.append(1)
        raise HTTPError('https://www.hl.co.uk/shares/test',403,'Forbidden',None,None)
    monkeypatch.setattr(hl,'urlopen',open_page)
    with pytest.raises(HTTPError):
        hl.fetch('https://www.hl.co.uk/shares/test')
    assert len(calls)==1


def test_same_day_cache_throttles_network_but_not_cached_reads(tmp_path,monkeypatch):
    from ftse_screener import hl
    calls,pauses=[],[]
    def fetch(url):
        calls.append(url)
        return 'public page'
    monkeypatch.setattr(hl,'fetch',fetch)
    get=hl.cached_fetch(tmp_path,pause=pauses.append)
    assert get('https://www.hl.co.uk/shares/test')=='public page'
    assert get('https://www.hl.co.uk/shares/test')=='public page'
    assert len(calls)==1
    assert pauses==[1]
    assert get.cache_stats['cached_pages']==1
    assert get.cache_stats['downloaded_pages']==1


def test_execution_source_failure_preserves_live_stock_data(monkeypatch):
    from ftse_screener import hl,execution,performance
    data=json.loads(Path('config/ftse_live.json').read_text())
    url='https://www.hl.co.uk/shares/shares-search-results/test'
    data['stocks']=[dict(isin='TEST',hl_url=url)]
    props=dict(investmentDetails=dict(isin='TEST',epicCode='TEST',title='Test',description='Ordinary',
        exchange=dict(current_timestamp='2026-10-16T08:00:00+01:00'),buy=dict(value=100,currency='GBX'),links={}),
        instrumentInfoOverview=dict(keyFacts=dict(sector='Industrials',industry='Engineering'),keyMetrics={}))
    monkeypatch.setattr(performance,'fetch_performance',lambda *args:{})
    def unavailable(*args): raise ValueError('Terms not verified')
    monkeypatch.setattr(execution,'parse_terms',unavailable)
    result=hl.refresh(data,get=lambda url:wrapped(props),pause=lambda seconds:None,full_metrics=True)
    assert len(result['stocks'])==1
    assert result['stocks'][0]['price']['value']=='100'
    assert result['execution_error']=='Terms not verified'
    assert 'hl_cutoff' not in result


def test_financial_cache_survives_rollover_and_expires(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from ftse_screener import hl
    start = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    financial = 'https://www.hl.co.uk/shares/test/financial-statements-and-reports'
    market = 'https://www.hl.co.uk/shares/test'
    calls = []
    monkeypatch.setattr(hl, 'fetch', lambda url: calls.append(url) or 'page')
    for elapsed in (0, 1, 6, 7):
        get = hl.cached_fetch(tmp_path, pause=lambda _: None, now=start+timedelta(days=elapsed))
        get(financial)
        get(market)
        expected = start.date() if elapsed < 7 else (start+timedelta(days=7)).date()
        assert get.observation_dates[financial] == expected
        assert get.cache_stats['financial_cached_pages'] == (1 if elapsed in (1, 6) else 0)
    assert calls.count(financial) == 2
    assert calls.count(market) == 4
    assert not (tmp_path / start.date().isoformat()).exists()


def test_financial_cache_invalid_timestamp_requires_download(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from ftse_screener import hl
    url = 'https://www.hl.co.uk/shares/test/financial-statements-and-reports'
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    calls = []
    monkeypatch.setattr(hl, 'fetch', lambda url: calls.append(url) or 'page')
    hl.cached_fetch(tmp_path, pause=lambda _: None, now=now)(url)
    next((tmp_path / 'financials').glob('*.json')).write_text('{"fetched_at_utc":"invalid"}')
    hl.cached_fetch(tmp_path, pause=lambda _: None, now=now)(url)
    assert len(calls) == 2


def test_refresh_preserves_cached_forecast_observation_date(monkeypatch):
    from datetime import date
    from ftse_screener import hl, fundamentals, performance, execution
    url = 'https://www.hl.co.uk/shares/test'
    financial = url + '/financial-statements-and-reports'
    original = date(2026, 10, 12)
    def get(url): return 'page'
    get.observation_dates = {financial: original}
    monkeypatch.setattr(hl, 'parse_factsheet', lambda *args: dict(
        isin='TEST', ticker='TEST', sector='Industrials', share_class='Ordinary',
        security_type='operating_company', metrics={}))
    monkeypatch.setattr(performance, 'fetch_performance', lambda *args: {})
    monkeypatch.setattr(fundamentals, 'financial_url', lambda *args: financial)
    seen = []
    def derive(html, source, observed, isin):
        seen.append(observed)
        return {'forecast_eps_growth_pct': dict(value='10', date=observed.isoformat(), source=source)}
    monkeypatch.setattr(fundamentals, 'derive_financials', derive)
    def unavailable(*args): raise ValueError('Terms unavailable')
    monkeypatch.setattr(execution, 'parse_terms', unavailable)
    result = hl.refresh(dict(policy={}, stocks=[dict(isin='TEST', hl_url=url)]), get=get,
                        pause=lambda _: None, full_metrics=True)
    assert seen == [original]
    assert result['stocks'][0]['metrics']['forecast_eps_growth_pct']['date'] == '2026-10-12'
