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


@pytest.mark.parametrize('today,market,expected', [
    ('2026-10-22', 'UK', '2026-10-23'),
    ('2026-10-24', 'US', '2026-10-26'),
    ('2026-10-09', 'US', '2026-10-13'),  # Columbus Day: bonds closed, NYSE open
    ('2026-11-10', 'US', '2026-11-12'),  # Veterans Day
    ('2026-12-31', 'UK', '2027-01-04'),
    ('2026-12-31', 'US', '2027-01-04'),
    ('2026-04-02', 'UK', '2026-04-07'),  # Easter bank holidays
])
def test_market_calendar_examples(today, market, expected):
    from datetime import date
    assert next_trading_day(date.fromisoformat(today), market) == date.fromisoformat(expected)


@pytest.mark.parametrize('module_name,market,arguments', [
    ('gilt_analyser.cli', 'UK', ['input.csv', '--investment', '5000']),
    ('us_treasury_analyser.cli', 'US', ['input.csv', '--investment', '5000']),
    ('us_corporate_analyser.cli', 'US', ['input.csv', '--investment', '5000']),
    ('us_corporate_analyser.public_fetcher', 'US', []),
])
@pytest.mark.parametrize('explicit', [None, '2026-10-25'])
def test_cli_settlement_defaults_and_overrides(module_name, market, arguments, explicit, monkeypatch):
    import argparse
    import importlib
    from datetime import date
    module = importlib.import_module(module_name)
    calls = []
    def default(requested_market):
        calls.append(requested_market)
        return date(2026, 10, 23)
    monkeypatch.setattr(module, 'default_settlement_date', default)
    monkeypatch.setattr(sys, 'argv', ['analyser', *arguments, *(['--settlement-date', explicit] if explicit else [])])
    original = argparse.ArgumentParser.parse_args
    class Parsed(Exception):
        pass
    def capture(parser, *args, **kwargs):
        parsed = original(parser, *args, **kwargs)
        assert parsed.settlement_date == date.fromisoformat(explicit or '2026-10-23')
        raise Parsed
    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', capture)
    with pytest.raises(Parsed):
        module.main()
    assert calls == [market]


def test_default_uses_london_date(monkeypatch):
    from datetime import date
    import gilt_analyser.trading_dates as dates
    class Clock:
        @staticmethod
        def now(zone):
            assert str(zone) == 'Europe/London'
            return datetime(2026, 10, 23, 23, 30, tzinfo=zone)
    monkeypatch.setattr(dates, 'datetime', Clock)
    assert dates.default_settlement_date('UK') == date(2026, 10, 26)


def test_unsupported_market():
    from datetime import date
    with pytest.raises(ValueError, match='Unsupported market'):
        next_trading_day(date(2026, 10, 22), 'UNKNOWN')
