import csv
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from openpyxl import load_workbook

from gilt_analyser.calculator import _xnpv
from gilt_analyser.models import CashFlow
from us_corporate_analyser.public_fetcher import (
    COLUMNS, fetch_records, parse_page, project_record, screen, write_discovery,
)

START = date(2026, 10, 19)
FETCHED = '2026-10-17T12:00:00+00:00'


@pytest.fixture
def record():
    return dict(cusip='DEMO00001', description='Synthetic regular bond', bondType='CORPORATE',
        bondStatus='OUTSTANDING', callable=False, nextCallDate=None, nextCallPrice=None,
        partialPar=False, perpetual=False, couponFrequency='SEMI_ANNUAL', rating='A-',
        maturityDate='2027-10-15', issueDate='2024-10-15', nextCouponDate='2027-04-15',
        coupon='6', currentPrice='.99', currentYield='7.1', parValue='1000',
        spOutlook='STABLE', spOutlookDate='2024-01-01')


def page(records, number=0, pages=1, total=None):
    return dict(content=records, number=number, totalPages=pages,
                totalElements=len(records) if total is None else total, numberOfElements=len(records))


def document(collection):
    return '<html><script type="application/json" id="__NEXT_DATA__">' + json.dumps(
        dict(props=dict(pageProps=dict(assetCollection=collection)))) + '</script></html>'


def project(record, start=START, budget=D('5000'), fee=D('10')):
    return project_record(record, start, budget, fee, 'A-', 24, FETCHED)


def test_public_cashflow_projection_is_explicitly_hypothetical(record):
    r = project(record)
    assert r['source_price_per_100'] == 99  # Source price fraction converted to per 100.
    assert r['assumed_accrued_interest_per_100'] == D('6')*4/360
    assert r['assumed_dirty_price_per_100'] == 99+D('6')*4/360
    assert r['assumed_nominal_purchased'] == 5000
    assert r['model_clean_consideration'] == 4950
    assert abs(r['model_accrued_interest_paid'] - D('5000')*D('6')*4/360/100) < D('.000000000000000000000001')
    assert r['model_total_initial_cost'] == r['model_clean_consideration']+r['model_accrued_interest_paid']+10
    assert r['model_unused_cash'] == 5000-r['model_total_initial_cost']
    assert r['model_coupon_income'] == 300
    assert r['model_redemption_proceeds'] == 5000
    assert r['model_redemption_gain'] == 50
    assert r['model_total_proceeds'] == 5300
    assert r['model_total_cash_profit'] == 5300-r['model_total_initial_cost']
    flows = (CashFlow(date(2027,4,15),D('150'),D('0')), CashFlow(date(2027,10,15),D('150'),D('5000')))
    assert abs(_xnpv(r['projected_annualised_return_pct']/100, r['model_total_initial_cost'], flows, START)) < D('.00000001')
    assert r['projected_annualised_return_pct'] < project(record, fee=D('0'))['projected_annualised_return_pct']
    assert r['review_status'].startswith('REVIEW')
    assert r['quote_timestamp'] == r['rating_effective_date'] == r['moodys'] == ''
    assert r['source_sp_outlook_date'] == '2024-01-01'  # Not repurposed as a rating date.
    assert r['source_ytw_pct'] == D('7.1')
    assert r['fetched_at_utc'] == FETCHED
    assert 'not verified' in r['assumptions']


def test_coupon_date_month_end_and_midperiod_accrual(record):
    r = deepcopy(record)
    r['maturityDate'], r['nextCouponDate'] = '2027-01-15', '2027-01-15'
    assert project(r, start=date(2026,7,15))['assumed_accrued_interest_per_100'] == 0
    # For a starting day below 30, US 30/360 retains an ending day of 31.
    assert project(r, start=date(2026,7,31))['assumed_accrued_interest_per_100'] == D('6')*16/360
    r['nextCouponDate'] = '2026-07-15'
    assert project(r, start=date(2026,4,15))['assumed_accrued_interest_per_100'] == D('1.5')


def test_projected_affordability_and_negative_yield(record):
    assert project(record,budget=D('4950'))['assumed_nominal_purchased'] == 4000
    with pytest.raises(ValueError, match='Unaffordable'):
        project(record,budget=D('990'))
    record['currentPrice'] = '1.2'
    assert project(record)['projected_annualised_return_pct'] < 0


@pytest.mark.parametrize('changes,reason', [
    ({'cusip':'89115A3A8'},'conflict'), ({'callable':True},'Callable'), ({'callable':None},'Callable'),
    ({'nextCallDate':'2027-01-01'},'Callable'), ({'nextCallPrice':'1'},'Callable'),
    ({'partialPar':True},'Fractional'), ({'perpetual':True},'Fractional'),
    ({'couponFrequency':'QUARTERLY'},'semiannual'), ({'rating':'BBB+'},'rating'),
    ({'rating':'NR'},'rating'), ({'rating':None},'rating'), ({'bondType':'TREASURY'},'corporate'),
    ({'bondStatus':'DEFAULTED'},'corporate'), ({'currentPrice':'NaN'},'currentPrice'),
    ({'coupon':'0'},'coupon'), ({'coupon':6.0},'coupon'), ({'currency':'EUR'},'USD'),
    ({'description':'Floating coupon'},'unsupported'), ({'parValue':'100'},'par value'),
    ({'maturityDate':'2029-10-15'},'window'), ({'maturityDate':'2026-10-19'},'window'),
    ({'maturityDate':'2027-10-31'},'Month-end'), ({'nextCouponDate':'2027-04-16'},'next coupon'),
    ({'issueDate':'2026-10-16'},'irregular'),
])
def test_unverified_and_unsupported_records_are_excluded(record, changes, reason):
    record.update(changes)
    rows, exclusions = screen([record],START,D('5000'),D('0'),'A-',24,FETCHED)
    assert rows == []
    assert reason in exclusions[0]['reason']


def test_local_filter_ranking_and_invalid_configuration(record):
    rows, excluded = screen([record,{**record,'cusip':'DEMO00002','rating':'BBB+'}],START,D('5000'),D('0'),'A-',24,FETCHED)
    assert len(rows) == len(excluded) == 1  # Do not trust server filters.
    assert rows[0]['rank'] == 1
    assert screen([record],START,D('5000'),D('0'),'AA-',24,FETCHED)[0] == []
    for budget,fee,rating,months in [(D('Infinity'),D(0),'A-',24),(D(5000),D(-1),'A-',24),
        (D(5),D(5),'A-',24),(D(5000),D(0),'BBB-',24),(D(5000),D(0),'A-',25)]:
        with pytest.raises(ValueError):
            screen([],START,budget,fee,rating,months,FETCHED)


def test_paging_complete_snapshots_and_query_parameters(record,tmp_path):
    calls=[]
    (tmp_path/'page-999.json').write_text('{}')
    def fetch(url):
        calls.append(url)
        n=int(parse_qs(urlparse(url).query)['pageNumber'][0])
        return document(page([{**record,'cusip':f'DEMO0000{n}'}],n,2,2))
    records,fetched=fetch_records(START,24,tmp_path,fetch=fetch)
    assert len(records) == 2
    assert not (tmp_path/'page-999.json').exists()
    assert fetched
    assert len(calls) == 2
    assert parse_qs(urlparse(calls[0]).query)['sortProperty'] == ['cusip']
    assert parse_qs(urlparse(calls[0]).query)['pageSize'] == ['1000']
    assert parse_qs(urlparse(calls[0]).query)['maxMaturityDate'] == ['2028-10-19']
    assert json.loads((tmp_path/'manifest.json').read_text())['total'] == 2
    assert json.loads((tmp_path/'page-001.json').read_text())['content'][0]['cusip'] == 'DEMO00001'


@pytest.mark.parametrize('case', ['duplicate','wrong_page','changed_total','truncated','too_many_pages','missing_data'])
def test_paging_fails_instead_of_returning_partial_universe(record,tmp_path,case):
    def fetch(url):
        n=int(parse_qs(urlparse(url).query)['pageNumber'][0])
        p=page([{**record,'cusip':f'DEMO0000{n}'}],n,2,2)
        if case=='duplicate':p['content'][0]['cusip']='DEMO00001'
        if case=='wrong_page':p['number']=0
        if case=='changed_total' and n:p['totalElements']=3
        if case=='truncated':p=page([record],0,1,2)
        if case=='too_many_pages':p['totalPages']=51
        if case=='missing_data':return '<html>Error</html>'
        return document(p)
    with pytest.raises(ValueError):
        fetch_records(START,24,tmp_path,fetch=fetch)


def test_empty_source_and_no_matches_are_explicit(tmp_path):
    records,_=fetch_records(START,24,tmp_path/'source',fetch=lambda u:document(page([],0,0,0)))
    assert records == []
    prefix=tmp_path/'empty'
    write_discovery([],[],prefix,'test')
    assert '0 research projections' in prefix.with_suffix('.md').read_text()
    assert load_workbook(prefix.with_suffix('.xlsx')).active.max_row == 1


def test_report_values_provenance_and_top50(record,tmp_path):
    rows,_=screen([record],START,D('5000'),D('10'),'A-',24,FETCHED)
    row=rows[0]
    row['name']='=HYPERLINK("example")'
    prefix=tmp_path/'report'
    write_discovery([row],[],prefix,'test')
    with prefix.with_suffix('.csv').open() as handle:
        output=next(csv.DictReader(handle))
    assert tuple(output)==COLUMNS
    assert 'source_ytw_pct' in output
    assert 'source_current_yield_pct' not in output
    assert D(output['source_ytw_pct']) == D(record['currentYield'])
    for key in COLUMNS:
        assert output[key] == str(row[key])
    sheet=load_workbook(prefix.with_suffix('.xlsx')).active
    assert sheet['A2'].data_type == 's'
    assert sheet.max_column == len(COLUMNS)
    headers = [cell.value for cell in sheet[1]]
    assert 'source_current_yield_pct' not in headers
    assert sheet.cell(2, headers.index('source_ytw_pct') + 1).value == float(D(record['currentYield']))
    summary=prefix.with_suffix('.md').read_text()
    assert 'Moody\'s is unavailable' in summary
    assert 'not an execution-cleared' in summary
    assert 'Fetch time is not quote time' in summary
    assert 'source_ytw_pct' in summary
    assert 'no separate source YTM is supplied' in summary
    many=[{**row,'cusip':f'DEMO{i:05d}'} for i in range(51)]
    write_discovery(many,[],prefix,'test')
    assert 'DEMO00049' in prefix.with_suffix('.md').read_text()
    assert 'DEMO00050' not in prefix.with_suffix('.md').read_text()


def test_return_band_then_maturity_order(record):
    early={**record,'cusip':'DEMO00002','maturityDate':'2027-04-15','nextCouponDate':'2027-04-15'}
    # Coupon differs to keep both annual projections in the 6.0-6.1% band.
    early['coupon']='6'
    record={**record,'currentPrice':'1'}
    early['currentPrice']='1'
    rows,_=screen([record,early],START,D('5000'),D('0'),'A-',24,FETCHED)
    assert len(rows)==2
    assert rows[0]['cusip']=='DEMO00002'


def test_failed_fetch_removes_old_success_manifest(tmp_path):
    (tmp_path/'manifest.json').write_text('{"old": true}')
    with pytest.raises(ValueError):
        fetch_records(START,24,tmp_path,fetch=lambda u:'<html>unavailable</html>')
    assert not (tmp_path/'manifest.json').exists()
