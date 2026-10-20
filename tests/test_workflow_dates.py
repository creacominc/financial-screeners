"""Exercise the Actions date-selection scripts with and without manual inputs."""
import os
from datetime import datetime
from gilt_analyser.trading_dates import next_trading_day
from pathlib import Path
import subprocess
import sys
import textwrap
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.parametrize('workflow', ['run-gilt-analysis.yml', 'run-us-treasury-analysis.yml', 'run-us-corporate-analysis.yml'])
@pytest.mark.parametrize('requested', ['', '2026-10-19'])
def test_bond_workflow_calculation_date(workflow, requested, tmp_path):
    content = (Path(__file__).resolve().parents[1] / '.github/workflows' / workflow).read_text()
    script = content.split('      - name: Select calculation date\n', 1)[1].split("          python - <<'PY'\n", 1)[1].split('          PY\n', 1)[0]
    output, summary = tmp_path / 'env', tmp_path / 'summary'
    before = datetime.now(ZoneInfo('Europe/London')).date().isoformat()
    result = subprocess.run([sys.executable, '-c', textwrap.dedent(script)], env={
        **os.environ, 'REQUESTED_DATE': requested, 'GITHUB_ENV': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
    }, capture_output=True, text=True)
    after = datetime.now(ZoneInfo('Europe/London')).date().isoformat()
    assert result.returncode == 0, result.stderr
    market = 'UK' if 'gilt' in workflow else 'US'
    expected = [requested] if requested else [next_trading_day(datetime.fromisoformat(d).date(), market).isoformat() for d in (before, after)]
    assert output.read_text().strip() in [f'COMPARISON_DATE={value}' for value in expected]
    assert 'not a broker-confirmed settlement date' in summary.read_text()


@pytest.mark.parametrize('market', ['UK', 'US'])
def test_next_trading_day_skips_weekends(market):
    from datetime import date
    assert next_trading_day(date(2026, 10, 23), market) == date(2026, 10, 26)


def test_next_trading_day_skips_us_christmas():
    from datetime import date
    assert next_trading_day(date(2026, 12, 24), 'US') == date(2026, 12, 28)


def test_next_trading_day_skips_uk_boxing_day_observed():
    from datetime import date
    assert next_trading_day(date(2026, 12, 24), 'UK') == date(2026, 12, 29)
