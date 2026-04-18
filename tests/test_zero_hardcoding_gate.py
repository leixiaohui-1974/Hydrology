from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_zero_hardcoding_gate_passes_for_workflow_tree() -> None:
    script = ROOT / "pipedream-hydrology-integration-lab" / "research" / "enforce_zero_hardcoding.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
