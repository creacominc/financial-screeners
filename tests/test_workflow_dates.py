"""Exercise the Actions date-selection scripts with and without manual inputs."""
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import textwrap
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.parametrize('workflow', ['run-gilt-analysis.yml', 'run-us-treasury-analysis.yml'])
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
    expected = [requested] if requested else [before, after]
    assert output.read_text().strip() in [f'COMPARISON_DATE={value}' for value in expected]
    assert 'not a broker-confirmed settlement date' in summary.read_text()
