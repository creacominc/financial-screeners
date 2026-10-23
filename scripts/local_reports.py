"""Run the four existing screeners and collect only successful current CSVs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from gilt_analyser.trading_dates import next_trading_day

ROOT = Path(__file__).resolve().parents[1]


def run_command(arguments, log, env):
    """Stream output to the terminal and preserve it for diagnosis."""
    command = [str(Path(sys.executable).parent / arguments[0]), *map(str, arguments[1:])]
    print('\nRunning: ' + ' '.join(map(str, arguments)), flush=True)
    with log.open('w') as output:
        with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True) as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                output.write(line)
            code = process.wait()
    if code:
        raise RuntimeError(f'{arguments[0]} failed (exit {code}). Log: {log}')


def generate(run, today, env):
    """Use existing CLI contracts without changing financial policy."""
    uk = next_trading_day(today, 'UK').isoformat()
    us = next_trading_day(today, 'US').isoformat()
    as_of = today.isoformat()
    details = run / 'details'
    details.mkdir()
    gilt = details / f'gilt-comparison-{uk}'
    treasury = details / f'us-treasury-comparison-{us}'
    corporate = details / f'us-corporate-research-{us}'
    ftse = details / f'ftse-comparison-{as_of}'
    input_csv = details / 'hl-current-gilts.csv'
    ftse_input = details / 'ftse_input.json'
    refreshed = details / 'ftse_refreshed.json'
    shutil.copyfile(ROOT / 'config/ftse_live.json', ftse_input)
    print(f'Gilt model settlement: {uk}; US bond model settlement: {us}; FTSE as-of: {as_of}.', flush=True)
    print('Settlement defaults are next market trading dates, not broker-confirmed dates.', flush=True)
    commands = [
        ['gilt-fetch-hl', input_csv, '--as-of', uk, '--months', '24'],
        ['gilt-analyser', input_csv, '--investment', '5000', '--fee', '11.95',
         '--settlement-date', uk, '--output', gilt],
        ['us-treasury-analyser', '--fetch-wsj', '--months', '24', '--investment', '5000',
         '--fee', '0', '--settlement-date', us, '--skip-unaffordable', '--output', treasury],
        ['us-corporate-fetch-public', '--settlement-date', us, '--investment', '5000',
         '--fee', '0', '--months', '24', '--minimum-sp', 'A-', '--output', corporate],
        ['ftse-fetch-hl', ftse_input, refreshed, '--discover-universe', '--full-metrics',
         '--cache-dir', ROOT / 'reports/hl-cache-local'],
        ['ftse-screener', refreshed, '--as-of', as_of, '--output', ftse],
    ]
    previous = ROOT / 'reports/local-ftse-history/previous.json'
    if previous.is_file():
        commands[-1].extend(['--previous-report', previous])
    for index, command in enumerate(commands, 1):
        run_command(command, details / f'{index:02d}-{command[0]}.log', env)
    sources = [prefix.with_suffix('.csv') for prefix in (gilt, treasury, corporate, ftse)]
    for source in sources:
        if not source.is_file():
            raise RuntimeError(f'Expected report missing: {source}')
    csv_folder = run / 'csv'
    csv_folder.mkdir()
    for source in sources:
        shutil.copyfile(source, csv_folder / source.name)
    previous.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ftse.with_suffix('.json'), previous)
    return csv_folder


def main():
    env = os.environ.copy()
    if sys.platform == 'darwin' and not env.get('SSL_CERT_FILE') and Path('/etc/ssl/cert.pem').is_file():
        env['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
    env['PYTHONUNBUFFERED'] = '1'
    now = datetime.now(ZoneInfo('Europe/London'))
    base = ROOT / 'reports/local-runs'
    base.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=now.strftime('%Y-%m-%d_%H%M%S-'), dir=base))
    print(f'Run files: {run}', flush=True)
    try:
        folder = generate(run, now.date(), env)
    except (OSError, RuntimeError) as error:
        print(f'\nFAILED: {error}\nPartial results: {run}\nNo completed CSV folder opened.', file=sys.stderr)
        return 1
    print(f'\nFour CSV reports ready: {folder}', flush=True)
    if sys.platform == 'darwin':
        subprocess.run(['open', str(folder)], check=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
