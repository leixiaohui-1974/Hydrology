"""Tests for scripts/backfill_workflow_reports_from_outcomes.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HYDROLOGY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HYDROLOGY_DIR.parent


def _load_backfill():
    path = REPO_ROOT / "scripts" / "backfill_workflow_reports_from_outcomes.py"
    spec = importlib.util.spec_from_file_location("backfill_wf_reports", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _minimal_outcome(case_id: str, workflow_key: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "contract_type": "workflow_outcome",
        "workflow_key": workflow_key,
        "case_id": case_id,
        "template_id": "generic_template",
        "status": "completed",
        "generated_at": "2026-04-14T00:00:00+00:00",
        "contract_path": f"cases/{case_id}/contracts/outcomes/{workflow_key}.latest.json",
        "dimensions": {
            "business": [],
            "process": [],
            "method": [],
            "result": [{"metric": "核心结果", "value": {"x": 1}, "confidence": 0.7}],
            "accuracy": [],
            "conclusion": [],
            "recommendation": [],
        },
        "artifacts": [],
        "metrics": {},
    }


class TestBackfillWorkflowReports(unittest.TestCase):
    def test_backfill_writes_reports(self) -> None:
        mod = _load_backfill()
        tmp = Path(tempfile.mkdtemp(prefix="hm_bf_"))
        try:
            cid = "bf_case"
            oc_dir = tmp / "cases" / cid / "contracts" / "outcomes"
            oc_dir.mkdir(parents=True)
            wf = "model"
            op = oc_dir / f"{wf}.latest.json"
            op.write_text(json.dumps(_minimal_outcome(cid, wf), ensure_ascii=False), encoding="utf-8")

            import workflows.outcome_contract as ocm
            from workflows import _reporting

            with patch.object(ocm, "WORKSPACE", tmp), patch.object(_reporting, "WORKSPACE", tmp):
                kind, msg = mod.backfill_one_outcome(
                    tmp,
                    op,
                    dry_run=False,
                    skip_existing=True,
                    force=False,
                )
            self.assertEqual(kind, "ok")
            self.assertTrue((tmp / "cases" / cid / "contracts" / f"{wf}_report.latest.json").is_file())
            self.assertTrue((tmp / "cases" / cid / "contracts" / f"{wf}_report.latest.md").is_file())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_skip_existing_skips_emit(self) -> None:
        mod = _load_backfill()
        tmp = Path(tempfile.mkdtemp(prefix="hm_bf2_"))
        try:
            cid = "bf_case2"
            cdir = tmp / "cases" / cid / "contracts"
            oc_dir = cdir / "outcomes"
            oc_dir.mkdir(parents=True)
            wf = "pipeline"
            op = oc_dir / f"{wf}.latest.json"
            op.write_text(json.dumps(_minimal_outcome(cid, wf), ensure_ascii=False), encoding="utf-8")
            (cdir / f"{wf}_report.latest.json").write_text("{}", encoding="utf-8")

            calls: list[str] = []

            def _fake_emit(**kwargs: object) -> dict:
                calls.append("emit")
                return {}

            kind, _msg = mod.backfill_one_outcome(
                tmp,
                op,
                dry_run=False,
                skip_existing=True,
                force=False,
                emit_fn=_fake_emit,
            )
            self.assertEqual(kind, "skipped")
            self.assertEqual(calls, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dry_run_no_emit(self) -> None:
        mod = _load_backfill()
        tmp = Path(tempfile.mkdtemp(prefix="hm_bf3_"))
        try:
            cid = "bf_case3"
            oc_dir = tmp / "cases" / cid / "contracts" / "outcomes"
            oc_dir.mkdir(parents=True)
            wf = "data_audit"
            op = oc_dir / f"{wf}.latest.json"
            op.write_text(json.dumps(_minimal_outcome(cid, wf), ensure_ascii=False), encoding="utf-8")

            calls: list[str] = []

            def _fake_emit(**kwargs: object) -> dict:
                calls.append("emit")
                return {}

            kind, _msg = mod.backfill_one_outcome(
                tmp,
                op,
                dry_run=True,
                skip_existing=False,
                force=True,
                emit_fn=_fake_emit,
            )
            self.assertEqual(kind, "dry_run")
            self.assertEqual(calls, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
