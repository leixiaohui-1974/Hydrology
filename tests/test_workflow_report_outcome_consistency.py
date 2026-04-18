"""Tests for scripts/check_workflow_report_outcome_consistency.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HYDROLOGY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HYDROLOGY_DIR.parent


def _load_consistency_module():
    path = REPO_ROOT / "scripts" / "check_workflow_report_outcome_consistency.py"
    spec = importlib.util.spec_from_file_location("wf_report_outcome_consistency", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWorkflowReportOutcomeConsistency(unittest.TestCase):
    def test_run_check_flags_missing_report_json(self) -> None:
        mod = _load_consistency_module()
        tmp = Path(tempfile.mkdtemp(prefix="hm_oc_rep_"))
        try:
            cid = "case_oc"
            oc_dir = tmp / "cases" / cid / "contracts" / "outcomes"
            oc_dir.mkdir(parents=True)
            (oc_dir / "model.latest.json").write_text("{}", encoding="utf-8")
            missing = mod.run_check(tmp, [cid], require_md=False)
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0].get("workflow_key"), "model")
            self.assertEqual(missing[0].get("reason"), "missing_report_json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_check_ok_when_report_json_exists(self) -> None:
        mod = _load_consistency_module()
        tmp = Path(tempfile.mkdtemp(prefix="hm_oc_rep_"))
        try:
            cid = "case_ok"
            cdir = tmp / "cases" / cid / "contracts"
            oc_dir = cdir / "outcomes"
            oc_dir.mkdir(parents=True)
            (oc_dir / "pipeline.latest.json").write_text("{}", encoding="utf-8")
            (cdir / "pipeline_report.latest.json").write_text("{}", encoding="utf-8")
            missing = mod.run_check(tmp, [cid], require_md=False)
            self.assertEqual(missing, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_require_md_flags_missing_md(self) -> None:
        mod = _load_consistency_module()
        tmp = Path(tempfile.mkdtemp(prefix="hm_oc_rep_"))
        try:
            cid = "case_md"
            cdir = tmp / "cases" / cid / "contracts"
            oc_dir = cdir / "outcomes"
            oc_dir.mkdir(parents=True)
            (oc_dir / "data_audit.latest.json").write_text("{}", encoding="utf-8")
            (cdir / "data_audit_report.latest.json").write_text("{}", encoding="utf-8")
            missing = mod.run_check(tmp, [cid], require_md=True)
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0].get("reason"), "missing_report_md")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_strict_exit_code(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="hm_oc_cli_"))
        try:
            cid = "case_cli"
            oc_dir = tmp / "cases" / cid / "contracts" / "outcomes"
            oc_dir.mkdir(parents=True)
            (oc_dir / "x.latest.json").write_text("{}", encoding="utf-8")
            script = REPO_ROOT / "scripts" / "check_workflow_report_outcome_consistency.py"
            base = [
                sys.executable,
                str(script),
                "--workspace-root",
                str(tmp),
                "--case-id",
                cid,
            ]
            r_strict = subprocess.run([*base, "--strict"], capture_output=True, text=True)
            self.assertEqual(r_strict.returncode, 1)
            r_loose = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(r_loose.returncode, 0)
            r_json = subprocess.run([*base, "--json"], capture_output=True, text=True)
            self.assertEqual(r_json.returncode, 0)
            data = json.loads(r_json.stdout)
            self.assertGreaterEqual(data.get("missing_count", 0), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
