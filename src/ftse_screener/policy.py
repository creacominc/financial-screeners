"""Explicit baseline scoring policy for the available public HL metrics."""
from copy import deepcopy


def metric(name, weight, low, high, direction='higher', positive_only=False, max_days=450):
    return dict(name=name,weight=str(weight),low=str(low),high=str(high),direction=direction,
                positive_only=positive_only,max_days=max_days)


OPERATING = dict(
    quality=[metric('roe',25,0,30), metric('operating_margin',20,0,30),
             metric('fcf_conversion',25,0,120),metric('net_debt_ebitda',15,0,5,'lower'),
             metric('earnings_consistency',15,0,100)],
    growth=[metric('eps_cagr_3y',35,-10,20),metric('revenue_cagr_3y',35,-5,15),
            metric('fcf_cagr_3y',15,-10,20),metric('forecast_eps_growth',15,-10,20,max_days=30)],
    valuation=[metric('pe',100,5,40,'lower',True,max_days=7)],
    trend=[metric('price_return_1y',50,-30,40,max_days=7),
           metric('price_return_3y',30,-30,100,max_days=7),metric('price_return_5y',20,-30,150,max_days=7)])
FINANCIAL = dict(
    quality=[metric('roe',70,0,20),metric('earnings_consistency',30,0,100)],
    growth=[metric('eps_cagr_3y',60,-10,20),metric('income_cagr_3y',40,-10,20)],
    valuation=deepcopy(OPERATING['valuation']), trend=deepcopy(OPERATING['trend']))


def populate_policy(data):
    """Opt-in baseline; explicit sector-specific overrides always take precedence."""
    if data['policy'].get('baseline_policy') != 'hl-public-v1':
        return
    policies = data['policy'].setdefault('sector_metrics', {})
    for stock in data['stocks']:
        financial = stock.get('industry','').lower()
        sector = stock['sector']
        if sector not in policies:
            policies[sector] = deepcopy(FINANCIAL if any(word in financial for word in ('bank','insurance'))
                                        or sector.lower() in ('banks','insurance','financial','financials','financial services') else OPERATING)
