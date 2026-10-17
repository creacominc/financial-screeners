"""Public HL indications and optional per-security purchase scenarios, not orders."""
import json
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING
from html.parser import HTMLParser
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .engine import affordability, number

TERMS_URL = 'https://www.hl.co.uk/investment-services/invest-by-direct-debit'
HOLIDAYS_URL = 'https://www.gov.uk/bank-holidays.json'
PRODUCTS = {'Stocks and Shares ISA':22, 'Fund and Share Account':98}


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
    def handle_data(self,data):
        self.parts.append(data)


def parse_terms(html, observed):
    parser=Text()
    parser.feed(html)
    text=' '.join(' '.join(parser.parts).split())
    minimum=re.search(r'minimum amount is £([0-9]+(?:\.[0-9]+)?) per investment',text,re.I)
    cutoff=re.search(r'fewer than (\d+) working days before the Direct Debit',text,re.I)
    collection=re.search(r'Direct Debits are taken from your bank account on the (\d+)(?:st|nd|rd|th)',text,re.I)
    no_fee="no charge to invest by Direct Debit" in text or "won't pay dealing charges" in text
    if not all((minimum,cutoff,collection,no_fee)) or 'FTSE-350 shares' not in text:
        raise ValueError('HL monthly terms changed or unavailable; cannot verify execution assumptions')
    return dict(minimum_gbp=minimum.group(1),fee_gbp='0',cutoff_working_days=int(cutoff.group(1)),
                collection_day=int(collection.group(1)),date=observed.isoformat(),source=TERMS_URL)


def next_cutoff(today, terms, holidays):
    """Conservative midnight deadline seven UK working days before collection."""
    holiday_dates={date.fromisoformat(e['date']) for e in holidays['england-and-wales']['events']}
    years={d.year for d in holiday_dates}
    def working(d):
        return d.weekday()<5 and d not in holiday_dates
    for offset in range(3):
        month=today.month-1+offset
        year=today.year+month//12
        if year not in years:
            raise ValueError('Official bank-holiday calendar does not cover collection year')
        collection=date(year,month%12+1,terms['collection_day'])
        while not working(collection):
            collection+=timedelta(days=1)
        cutoff=collection
        remaining=terms['cutoff_working_days']
        while remaining:
            cutoff-=timedelta(days=1)
            if working(cutoff): remaining-=1
        if cutoff>today:
            return datetime.combine(cutoff,datetime.min.time(),ZoneInfo('Europe/London')).isoformat()
    raise ValueError('No upcoming instruction cutoff')


def fetch_holidays():
    with urlopen(HOLIDAYS_URL,timeout=30) as response:
        return json.loads(response.read())


def account_scenarios(stock, data, today, terms, cutoff):
    results=[]
    for account in data.get('accounts',list(PRODUCTS)):
        if account not in PRODUCTS:
            raise ValueError('Unsupported account')
        indicated=(stock.get('internet_tradable') is True and PRODUCTS[account] in stock.get('hl_account_products',[])
                   and stock.get('membership',{}).get('ftse350') is True
                   and stock.get('security_type') == 'operating_company')
        estimate=dict(account=account, eligibility='PUBLICLY_INDICATED' if indicated else 'UNVERIFIED',
                      eligibility_reason='Current public FTSE350 listing, exact share-class account availability and general HL monthly terms; confirm in Monthly Savings before submission' if indicated else 'Exact class/account/monthly eligibility unresolved',
                      eligibility_sources=[stock['hl_url'],terms['source']],checked_date=terms['date'],cutoff=cutoff)
        estimate['proposed_action']='Consider adding or increasing monthly purchase'
        if stock.get('gate_status') == 'REVIEW':
            estimate['proposed_action']='Resolve gate review before considering purchase'
        contribution=data.get('monthly_per_share_gbp')
        review=data.get('security_reviews',{}).get(stock['isin'],{})
        tax=review.get('purchase_tax_rate')
        if contribution is None or tax is None or not indicated:
            estimate.update(dca_status='UNVERIFIED',dca_reason='Enter a monthly amount per share and verify applicable purchase costs/eligibility',estimated_shares=None,residual_gbp=None)
        else:
            instruction=dict(eligible=True,account=account,date=terms['date'],source=terms['source'],
                             cutoff=cutoff,contribution_gbp=contribution,minimum_gbp=terms['minimum_gbp'],
                             fee_gbp=terms['fee_gbp'],purchase_tax_rate=tax)
            estimate.update(affordability(dict(stock,execution=instruction),data['policy'],today))
            estimate['contribution_gbp']=contribution
        price=stock.get('price',{})
        if price.get('value') is not None and price.get('currency') in ('GBP','GBX') and tax is not None:
            p=number(price['value'])/(100 if price['currency']=='GBX' else 1)
            cost=(p*(1+number(tax))+number(terms['fee_gbp'])).quantize(number('.01'),rounding=ROUND_CEILING)
            estimate['minimum_for_one_share_gbp']=max(number(terms['minimum_gbp']),cost)
        results.append(estimate)
    return results
