"""Verify collection never presents stale or partial runs as four current CSVs."""
from datetime import date
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('local_reports', Path('scripts/local_reports.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/ftse_live.json').write_text('{}')
    monkeypatch.setattr(local, 'ROOT', tmp_path)
    run = tmp_path / 'run'
    run.mkdir()
    return run


def fake_report(command, log, env):
    log.write_text('completed')
    if '--output' in command:
        prefix = Path(command[command.index('--output') + 1])
        prefix.with_suffix('.csv').write_text('company\nexample\n')
        prefix.with_suffix('.json').write_text('{}')
        # Extra CSVs must not leak into the four-file results folder.
        Path(str(prefix) + '_excluded.csv').write_text('excluded\n')


def test_collects_exactly_four_current_csvs_with_market_dates_and_history(workspace, monkeypatch):
    commands = []
    def execute(command, log, env):
        commands.append(command)
        fake_report(command, log, env)
    monkeypatch.setattr(local, 'run_command', execute)
    csv = local.generate(workspace, date(2026, 10, 23), {})
    assert {p.name for p in csv.iterdir()} == {
        'gilt-comparison-2026-10-26.csv', 'us-treasury-comparison-2026-10-26.csv',
        'us-corporate-research-2026-10-26.csv', 'ftse-comparison-2026-10-23.csv'}
    assert (local.ROOT / 'reports/local-ftse-history/previous.json').is_file()
    assert '--universe-source' not in commands[-2]
    second = local.ROOT / 'second'
    second.mkdir()
    local.generate(second, date(2026, 10, 23), {})
    assert '--previous-report' in commands[-1]
    assert len(list(csv.iterdir())) == 4


def test_command_failure_does_not_publish_csv_folder_or_history(workspace, monkeypatch):
    def execute(command, log, env):
        if command[0] == 'us-treasury-analyser':
            raise RuntimeError('download failed')
        fake_report(command, log, env)
    monkeypatch.setattr(local, 'run_command', execute)
    with pytest.raises(RuntimeError, match='download failed'):
        local.generate(workspace, date(2026, 10, 23), {})
    assert not (workspace / 'csv').exists()
    assert not (local.ROOT / 'reports/local-ftse-history/previous.json').exists()


def test_missing_csv_does_not_publish_results(workspace, monkeypatch):
    monkeypatch.setattr(local, 'run_command', lambda *args: None)
    with pytest.raises(RuntimeError, match='Expected report missing'):
        local.generate(workspace, date(2026, 10, 23), {})
    assert not (workspace / 'csv').exists()
