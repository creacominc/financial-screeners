from datetime import date
from decimal import Decimal as D

import pytest

from gilt_analyser.summary import write_summary


@pytest.mark.parametrize('treasury', [False, True])
def test_summary_matches_existing_ranking_and_limits_fifty(tmp_path, treasury):
    if treasury:
        from us_treasury_analyser.calculator import Treasury, analyse_treasury
        from us_treasury_analyser.reporting import ranked_rows
        analyses = [analyse_treasury(Treasury(f'TEST{i:05}', f'Bond {i}', 'note', D('4'), date(2028, 1, 1), D(95)+D(i)/100), date(2026, 1, 1), D(5000), D(1)) for i in range(55)]
    else:
        from gilt_analyser.models import Gilt
        from gilt_analyser.calculator import analyse_gilt
        from gilt_analyser.reporting import ranked_rows
        analyses = [analyse_gilt(Gilt(f'TEST{i:05}', f'Bond {i}', D('4'), date(2028, 1, 1), D(95)+D(i)/100), date(2026, 1, 1), D(5000), D(1)) for i in range(55)]
    rows = ranked_rows(list(reversed(analyses)))
    text = write_summary(rows, tmp_path/'summary', treasury=treasury, source='supplied.csv', settlement=date(2026, 1, 1), budget=D(5000), fee=D(1)).read_text()
    assert 'Analysed: **55**; shown: **50**' in text
    positions = [text.index(f"| {r['rank']} | {r['name']} |") for r in rows[:50]]
    assert positions == sorted(positions)
    assert f"| 51 | {rows[50]['name']} |" not in text
    first = rows[0]
    assert f"{first['net_annualised_return_pct']:,.2f}" in text
    assert f"{first['total_cash_profit']:,.2f}" in text
    assert '| Name | Months to maturity | Net annualised return % |' in text
    assert ('Deployed USD' if treasury else 'Deployed GBP') in text
    assert 'Broker YTM %' in text if treasury else 'CGT-exempt redemption gain GBP' in text


def test_empty_summary_exclusions_and_markdown_escaping(tmp_path):
    excluded = [dict(cusip='ABC', name='A|B<script>\nC', reason='Cost > budget')]
    text = write_summary([], tmp_path/'empty', treasury=True, source='example.csv', excluded=excluded).read_text()
    assert 'No affordable selections' in text
    assert 'excluded as unaffordable: **1**' in text
    assert 'A&#124;B&lt;script&gt; C' in text
    assert 'Cost &gt; budget' in text
