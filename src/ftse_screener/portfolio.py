"""Optional ownership context; never invent current positions or contribution budgets."""
from decimal import Decimal
from .engine import number


def apply_holdings(data):
    positions = data.get('holdings', [])
    grouped = {}
    for position in positions:
        if position['account'] not in ('Stocks and Shares ISA','Fund and Share Account'):
            raise ValueError('Unknown HL account type in holdings')
        value = number(position['value_gbp'])
        if value < 0:
            raise ValueError('Negative holding value')
        grouped.setdefault(position['isin'],[]).append(position)
    known={stock['isin'] for stock in data['stocks']}
    data['unresolved_holdings']=[dict(p,gate_status='REVIEW',reason='Holding is outside fetched universe and has no supplied security record') for p in positions if p['isin'] not in known]
    for stock in data['stocks']:
        if stock['isin'] in grouped:
            stock['holding'] = True
            stock['positions'] = grouped[stock['isin']]
            stock['holding_value_gbp'] = str(sum((number(p['value_gbp']) for p in stock['positions']), Decimal(0)))
