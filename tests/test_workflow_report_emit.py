"""Tests for workflows._reporting.emit_workflow_report and run_workflow integration."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import workflows
import workflows.outcome_contract as outcome_contract_mod
from workflows import _reporting
from workflows._reporting import emit_workflow_report, write_report_emit_error_sidecar


class TestEmitWorkflowReport(unittest.TestCase):
    def test_writes_md_and_json_under_contracts(self) -> None:
        tmp = Path(self._temp_dir())
        case_id = "emit_report_test_case"
        wf = "model"
        cdir = tmp / "cases" / case_id / "contracts"
        cdir.mkdir(parents=True, exist_ok=True)

        outcome = {
            "schema_version": "1.0.0",
            "contract_type": "workflow_outcome",
            "workflow_key": wf,
            "case_id": case_id,
            "template_id": "generic_template",
            "status": "completed",
            "generated_at": "2026-04-13T00:00:00+00:00",
            "contract_path": f"cases/{case_id}/contracts/outcomes/{wf}.latest.json",
            "dimensions": {
                "business": [{"metric": "目标", "value": "测试", "confidence": 0.9}],
                "process": [{"metric": "执行状态", "value": "completed", "confidence": 0.95}],
                "method": [{"metric": "模板ID", "value": "generic_template", "confidence": 0.9}],
                "result": [
                    {
                        "metric": "核心结果",
                        "value": {"model_type": "lstm", "config": {"seq_len": 24}},
                        "confidence": 0.7,
                    }
                ],
                "accuracy": [],
                "conclusion": [{"metric": "结论", "value": "ok", "evidence_path": "x.md"}],
                "recommendation": [],
            },
            "artifacts": [{"path": "cases/foo/bar.json", "exists": True, "artifact_type": "json"}],
            "metrics": {"nse": 0.9},
        }

        with patch.object(_reporting, "WORKSPACE", tmp):
            doc = emit_workflow_report(
                case_id=case_id,
                workflow_key=wf,
                outcome_contract=outcome,
            )

        md_path = tmp / "cases" / case_id / "contracts" / f"{wf}_report.latest.md"
        js_path = tmp / "cases" / case_id / "contracts" / f"{wf}_report.latest.json"
        self.assertTrue(md_path.is_file(), msg="markdown report missing")
        self.assertTrue(js_path.is_file(), msg="json sidecar missing")
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("工作流报告", text)
        self.assertIn("lstm", text)
        self.assertIn("## 2. 输出证据", text)
        self.assertIn("## 3. 输入资产", text)

        payload = json.loads(js_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("contract_type"), "workflow_human_report")
        self.assertEqual(payload.get("workflow_key"), wf)
        self.assertEqual(payload.get("workflow_run_id"), payload.get("run_id"))
        self.assertIsInstance(payload.get("dependencies"), list)
        self.assertIn(payload.get("outcome_contract_path"), payload["dependencies"])
        self.assertEqual(payload.get("gaps"), [])
        models = payload.get("executed_models") or []
        keys = {m.get("key") for m in models if isinstance(m, dict)}
        self.assertIn("model_type", keys)
        self.assertIn("seq_len", keys)

        self.assertIn("written_paths", doc)
        self.assertEqual(doc["written_paths"]["json"], str(js_path.relative_to(tmp)))

    def test_explicit_executed_models_candidates_and_gaps_in_sidecar(self) -> None:
        tmp = Path(self._temp_dir())
        case_id = "emit_merge_case"
        wf = "dl_forecast"
        outcome = {
            "schema_version": "1.0.0",
            "contract_type": "workflow_outcome",
            "workflow_key": wf,
            "case_id": case_id,
            "template_id": "forecast_template",
            "status": "completed",
            "generated_at": "2026-04-13T01:00:00+00:00",
            "contract_path": f"cases/{case_id}/contracts/outcomes/{wf}.latest.json",
            "validation_errors": ["dim.x.missing"],
            "dimensions": {
                "business": [],
                "process": [],
                "method": [],
                "result": [
                    {
                        "metric": "核心结果",
                        "value": {
                            "executed_models": [
                                {
                                    "registry": "explicit",
                                    "key": "primary_model",
                                    "version": "2.1",
                                }
                            ],
                            "candidate_models_not_run": ["timesfm", {"name": "lstm", "reason": "budget"}],
                            "report_input_assets": [
                                {"path": "cases/x/dem.tif", "role": "DEM"},
                            ],
                            "model_type": "transformer",
                        },
                        "confidence": 0.7,
                    }
                ],
                "accuracy": [],
                "conclusion": [],
                "recommendation": [],
            },
            "artifacts": [],
            "metrics": {},
        }
        with patch.object(_reporting, "WORKSPACE", tmp):
            doc = emit_workflow_report(case_id=case_id, workflow_key=wf, outcome_contract=outcome)

        md = (tmp / "cases" / case_id / "contracts" / f"{wf}_report.latest.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## 4.1 配置候选但未运行", md)
        self.assertIn("timesfm", md)
        self.assertIn("dem.tif", md)
        self.assertIn("primary_model", md)
        self.assertIn("transformer", md)

        payload = json.loads(
            (tmp / "cases" / case_id / "contracts" / f"{wf}_report.latest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload.get("gaps"), ["dim.x.missing"])
        cnr = payload.get("candidate_models_not_run") or []
        self.assertEqual(len(cnr), 2)
        models = payload.get("executed_models") or []
        prim = next((m for m in models if m.get("key") == "primary_model"), None)
        self.assertIsNotNone(prim)
        self.assertEqual(prim.get("version"), "2.1")
        keys = {m.get("key") for m in models if isinstance(m, dict)}
        self.assertIn("model_type", keys)

    def test_write_report_emit_error_sidecar(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="hm_emit_err_"))
        try:
            with patch.object(_reporting, "WORKSPACE", tmp):
                p = write_report_emit_error_sidecar(
                    case_id="c1",
                    workflow_key="wf1",
                    error_message="disk full",
                    exc_type="OSError",
                )
            self.assertIsNotNone(p)
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data.get("contract_type"), "workflow_report_emit_error")
            self.assertEqual(data.get("error"), "disk full")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _temp_dir(self) -> str:
        return tempfile.mkdtemp(prefix="hm_wf_report_")


class TestRunWorkflowReportEmitIntegration(unittest.TestCase):
    """Patch WORKSPACE so outcomes + reports land in a temp dir."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hm_rwf_emit_"))
        self._ut_mod_names: list[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        for name in self._ut_mod_names:
            sys.modules.pop(name, None)

    def _register_ut(self, key: str, fn) -> None:
        mod_name = f"workflows._ut_emit_{key}"
        m = types.ModuleType(mod_name)
        m.run_ut = fn  # type: ignore[attr-defined]
        sys.modules[mod_name] = m
        self._ut_mod_names.append(mod_name)
        workflows.WORKFLOW_REGISTRY[key] = {
            "module": mod_name,
            "entry": "run_ut",
            "description": "UT workflow report emit",
            "required_args": ["case_id"],
        }

    def test_run_workflow_success_writes_report_files(self) -> None:
        key = "_ut_emit_success"
        case_id = "ut_case_success"

        def _run(case_id: str) -> dict:
            return {"lane": "ok", "case_id": case_id}

        self._register_ut(key, _run)
        try:
            with patch.object(outcome_contract_mod, "WORKSPACE", self.tmp), patch.object(
                _reporting, "WORKSPACE", self.tmp
            ):
                out = workflows.run_workflow(key, case_id=case_id)
        finally:
            workflows.WORKFLOW_REGISTRY.pop(key, None)

        self.assertEqual(out.get("lane"), "ok")
        md = self.tmp / "cases" / case_id / "contracts" / f"{key}_report.latest.md"
        js = self.tmp / "cases" / case_id / "contracts" / f"{key}_report.latest.json"
        self.assertTrue(md.is_file(), msg="expected human report md")
        self.assertTrue(js.is_file(), msg="expected report sidecar json")

    def test_emit_failure_sets_report_emit_error_on_dict_result(self) -> None:
        key = "_ut_emit_err_on_result"
        case_id = "ut_case_emit_err"

        def _run(case_id: str) -> dict:
            return {"x": 1}

        self._register_ut(key, _run)
        try:
            with (
                patch.object(outcome_contract_mod, "WORKSPACE", self.tmp),
                patch.object(_reporting, "WORKSPACE", self.tmp),
                patch.object(workflows, "emit_workflow_report", side_effect=ValueError("emit_boom")),
            ):
                out = workflows.run_workflow(key, case_id=case_id)
        finally:
            workflows.WORKFLOW_REGISTRY.pop(key, None)

        self.assertEqual(out.get("x"), 1)
        self.assertIn("report_emit_error", out)
        self.assertIn("emit_boom", out["report_emit_error"])

    def test_workflow_failure_emit_failure_writes_error_sidecar(self) -> None:
        key = "_ut_emit_fail_chain"
        case_id = "ut_case_fail_chain"

        def _run(case_id: str) -> dict:
            raise RuntimeError("wf_boom")

        self._register_ut(key, _run)
        try:
            with (
                patch.object(outcome_contract_mod, "WORKSPACE", self.tmp),
                patch.object(_reporting, "WORKSPACE", self.tmp),
                patch.object(workflows, "emit_workflow_report", side_effect=OSError("emit_fail")),
            ):
                with self.assertRaises(RuntimeError):
                    workflows.run_workflow(key, case_id=case_id)
        finally:
            workflows.WORKFLOW_REGISTRY.pop(key, None)

        sidecar = (
            self.tmp
            / "cases"
            / case_id
            / "contracts"
            / f"{key}_report_emit_error.latest.json"
        )
        self.assertTrue(sidecar.is_file())
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("contract_type"), "workflow_report_emit_error")
        self.assertIn("emit_fail", payload.get("error", ""))


if __name__ == "__main__":
    unittest.main()
