"""Markdown summaries of already-calculated, ranked bond results."""
from decimal import Decimal
from pathlib import Path


def cell(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, Decimal):
        value = f'{value:,.2f}'
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def table(headers, records):
    return ['| ' + ' | '.join(headers) + ' |',
            '| ' + ' | '.join('---' for _ in headers) + ' |'] + [
                '| ' + ' | '.join(cell(v) for v in record) + ' |' for record in records]


def write_summary(rows, prefix: Path, *, treasury=False, source='', excluded=(), settlement=None, budget=None, fee=None):
    """Use report order verbatim; never recalculate yields or mix currencies."""
    currency = 'USD' if treasury else 'GBP'
    title = 'US Treasury' if treasury else 'UK gilt'
    selected = rows[:50]
    lines = [f'# {title} screening summary', '',
             f'Settlement: {cell(settlement)}. Budget per security: {cell(budget)} {currency}; dealing fee: {cell(fee)} {currency}.', '',
             f'Input: {cell(source)}. Analysed: **{len(rows)}**; shown: **{len(selected)}**; excluded as unaffordable: **{len(excluded)}**.', '',
             'Each row is an alternative use of the same budget, not a combined portfolio allocation. Rankings match the CSV/XLSX: descending 0.1 percentage-point yield band, then shorter maturity, precise yield and security identifier.', '',
             'Net annualised return is the annual effective money-weighted return after the dealing fee and before personal income tax, assuming purchase at the supplied clean offer price and holding to maturity. Annualised yield is shown alongside actual cash profit; short maturities can magnify annualised figures.', '',
             '## Top 50 ranked selections', '']
    if selected:
        lines += table(['Rank', 'Name', 'Months to maturity', 'Net annualised return %', 'ISIN' if not treasury else 'CUSIP / security ID', 'Maturity', 'Clean price /100', f'Deployed {currency}', f'Coupon income {currency}', f'Cash profit {currency}', f'Unused {currency}'], [
            [r['rank'], r['name'], r['months_to_maturity'], r['net_annualised_return_pct'],
             (r.get('cusip') or r.get('security_id')) if treasury else r['isin'], r['maturity_date'],
             r['clean_buy_price_per_100'], r['total_initial_cost'], r['coupon_income'], r['total_cash_profit'], r['unused_cash']]
            for r in selected])
        lines += ['', '## Quote and calculation details', '']
        if treasury:
            lines += ['Quote status and source dates are retained below. Indicative WSJ quotes are research inputs; broker lots, available quantities and executable prices require confirmation. Broker YTM is separate from the calculated return above. No GBP conversion is applied.', '']
            lines += table(['Rank', 'Type', 'Quote status', 'Quote date', 'Source', 'Broker YTM %', 'Quantity basis', 'Analysis minimum nominal', 'Analysis increment', 'Nominal purchased'], [
                [r['rank'], r['security_type'], r['quote_status'], r['quote_date'], r['price_source'], r['broker_ytm_pct'], r['quantity_basis'], r['analysis_minimum_nominal'], r['analysis_nominal_increment'], r['nominal_purchased']] for r in selected])
        else:
            lines += ['Input prices are used as supplied; the settlement date is not proof of quote freshness. Current HL fetches and repository example inputs are identified by the input label above. The model assumes regular coupons and cum-dividend settlement.', '',
                      'The conventional-gilt UK CGT-exempt redemption gain is redemption proceeds less clean consideration. Accrued interest and dealing fees remain costs in total cash profit.', '']
            lines += table(['Rank', 'HL code', 'Coupon %', 'Accrued /100', 'Dirty /100', 'Nominal purchased', 'CGT-exempt redemption gain GBP'], [
                [r['rank'], r['hl_code'], r['coupon_rate_pct'], r['accrued_interest_per_100'], r['dirty_price_per_100'], r['nominal_purchased'], r['cgt_exempt_redemption_gain']] for r in selected])
    else:
        lines += ['No affordable selections were produced.']
    if excluded:
        lines += ['', '## Unaffordable exclusions', '', f'{len(excluded)} offers excluded. Full exclusions are retained in the exclusions CSV.', '']
        lines += table(['Identifier', 'Name', 'Reason'], [[r.get('cusip') or r.get('security_id'), r['name'], r['reason']] for r in excluded[:50]])
    lines += ['', 'Download the report artifacts for all ranked rows and full precision values.', '']
    path = prefix.with_suffix('.md')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path
