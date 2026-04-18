from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_gateway_module():
    module_path = ROOT_DIR / "workflows" / "agent_loop_gateway.py"
    spec = importlib.util.spec_from_file_location("agent_loop_gateway_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestAgentLoopGatewayVisibleWorkflows(unittest.TestCase):
    def _write_config(self, root: Path, allowlist: list[str]) -> Path:
        config_path = root / "agent_visible_workflows.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "defaults": {"enabled": True, "mode": "allowlist"},
                    "allowlist": allowlist,
                    "aliases": {
                        "wxq_mine": "knowledge_mine",
                        "wxq_sync": "source_sync",
                        "legacy_hydro_coupling_ext": "coupled",
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return config_path

    def _write_manifest(self, workspace: Path, case_id: str, workflow_targets: list[str]) -> None:
        manifest_path = workspace / "cases" / case_id / "manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            yaml.safe_dump({"workflow_targets": workflow_targets}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def test_list_tools_applies_global_allowlist_before_case_targets(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["acceptance_review", "release_publish"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            tools, policy = gateway._filter_tools_for_case(root, "demo")
            names = [tool["name"] for tool in tools]

            self.assertEqual(
                names,
                [
                    "case_knowledge_lint",
                    "bootstrap_case_triad_minimal",
                    "delivery_docs_pack_dry_run",
                    "smart_meta",
                    "smart_plan",
                    "smart_run",
                    "smart_refresh_reports",
                    "smart_status",
                ],
            )
            self.assertEqual(policy["agent_visible_workflows"]["allowlist"], ["init"])
            self.assertEqual(policy["filter_mode"], "manifest_workflow_targets")

    def test_list_tools_hides_bootstrap_when_init_not_visible(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["acceptance_review", "release_publish"])
            config_path = self._write_config(root, ["model"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            tools, _policy = gateway._filter_tools_for_case(root, "demo")
            names = [tool["name"] for tool in tools]

            self.assertEqual(
                names,
                [
                    "case_knowledge_lint",
                    "delivery_docs_pack_dry_run",
                    "smart_meta",
                    "smart_plan",
                    "smart_run",
                    "smart_refresh_reports",
                    "smart_status",
                ],
            )

    def test_invoke_tool_rejects_globally_hidden_bootstrap_tool(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["acceptance_review", "release_publish"])
            config_path = self._write_config(root, ["model"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            result = gateway._handle(
                {"op": "invoke_tool", "tool": "bootstrap_case_triad_minimal", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "tool_not_visible_globally")
            self.assertEqual(result["required_workflow_keys"], ["init"])

    def test_delivery_tool_still_depends_on_case_targets(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            tools, _policy = gateway._filter_tools_for_case(root, "demo")
            names = [tool["name"] for tool in tools]

            self.assertEqual(
                names,
                [
                    "case_knowledge_lint",
                    "bootstrap_case_triad_minimal",
                    "smart_meta",
                    "smart_plan",
                    "smart_run",
                    "smart_refresh_reports",
                    "smart_status",
                ],
            )

    def test_invoke_smart_status_returns_contract_artifact_presence(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path
            contracts = root / "cases" / "demo" / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            shared_cli_result = contracts / "workflow_smart_cli_result.latest.json"
            scoped_cli_result = contracts / "workflow_smart_cli_result.run.smart.latest.json"
            shared_cli_result.write_text("{}\n", encoding="utf-8")
            scoped_cli_result.write_text("{}\n", encoding="utf-8")

            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_status", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["tool"], "smart_status")
            self.assertEqual(result["case_id"], "demo")
            self.assertTrue(result["result"]["exists"]["cli_result"])
            self.assertTrue(result["result"]["exists"]["default_scoped_cli_result"])
            self.assertFalse(result["result"]["exists"]["run_summary"])
            self.assertTrue(result["result"]["shared_cli_result_exists"])
            self.assertTrue(result["result"]["scoped_cli_result_exists"])
            self.assertTrue(result["result"]["shared_cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertTrue(result["result"]["scoped_cli_result_path"].endswith("workflow_smart_cli_result.run.smart.latest.json"))
            self.assertTrue(result["result"]["cli_result_exists"])
            self.assertTrue(result["result"]["cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertTrue(result["result"]["latest_cli_result"].endswith("workflow_smart_cli_result.latest.json"))

    def test_invoke_smart_status_reports_scoped_result_without_shared_latest(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path
            contracts = root / "cases" / "demo" / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            scoped_cli_result = contracts / "workflow_smart_cli_result.run.smart.latest.json"
            scoped_cli_result.write_text("{}\n", encoding="utf-8")

            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_status", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["result"]["shared_cli_result_exists"])
            self.assertTrue(result["result"]["scoped_cli_result_exists"])
            self.assertFalse(result["result"]["cli_result_exists"])
            self.assertTrue(result["result"]["cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertIsNone(result["result"]["latest_cli_result"])
            self.assertTrue(result["result"]["scoped_cli_result_path"].endswith("workflow_smart_cli_result.run.smart.latest.json"))

    def test_direct_smart_status_op_is_accepted(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path
            contracts = root / "cases" / "demo" / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)

            result = gateway._handle(
                {"op": "smart_status", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["tool"], "smart_status")
            self.assertEqual(result["case_id"], "demo")

    def test_direct_smart_plan_op_is_accepted(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            calls: list[list[str]] = []

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                calls.append(argv)
                return {"returncode": 0, "stdout_tail": "{}", "stderr_tail": "", "ok": True}

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "smart_plan", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["tool"], "smart_plan")
            self.assertIn("plan", calls[0])

    def test_invoke_smart_meta_does_not_require_case_id(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            calls: list[list[str]] = []

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                calls.append(argv)
                return {"returncode": 0, "stdout_tail": "{}", "stderr_tail": "", "ok": True}

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_meta"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["case_id"], "")
            self.assertIn("meta", calls[0])

    def test_smart_plan_passes_visible_allowlist_to_cli(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            calls: list[list[str]] = []

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                calls.append(argv)
                return {"returncode": 0, "stdout_tail": "{}", "stderr_tail": "", "ok": True}

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_plan", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertIn("--restrict-workflow-keys", calls[0])
            self.assertIn("init", calls[0])
            self.assertTrue(result["shared_cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertTrue(result["scoped_cli_result_path"].endswith("workflow_smart_cli_result.plan.smart.latest.json"))
            self.assertFalse(result["shared_cli_result_exists"])
            self.assertFalse(result["scoped_cli_result_exists"])
            self.assertIsNone(result["latest_cli_result"])

    def test_smart_run_passes_visible_allowlist_to_cli(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            calls: list[list[str]] = []
            timeouts: list[int] = []

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                calls.append(argv)
                timeouts.append(timeout)
                return {"returncode": 0, "stdout_tail": "{}", "stderr_tail": "", "ok": True}

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_run", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertIn("--restrict-workflow-keys", calls[0])
            self.assertIn("init", calls[0])
            self.assertEqual(timeouts, [1800])
            self.assertIsNone(result["latest_cli_result"])
            self.assertTrue(result["shared_cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertTrue(result["scoped_cli_result_path"].endswith("workflow_smart_cli_result.run.smart.latest.json"))
            self.assertFalse(result["shared_cli_result_exists"])
            self.assertFalse(result["scoped_cli_result_exists"])

    def test_oneshot_invalid_json_returns_structured_error(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT_DIR / "workflows" / "agent_loop_gateway.py"),
                "--oneshot",
                "{bad",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "invalid_json")

    def test_oneshot_non_object_returns_structured_error(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT_DIR / "workflows" / "agent_loop_gateway.py"),
                "--oneshot",
                "[]",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "message_not_object")

    def test_run_argv_returns_structured_timeout_payload(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            timeout_error = subprocess.TimeoutExpired(
                cmd=["python3", "demo.py"],
                timeout=12,
                output=b"partial stdout",
                stderr=b"partial stderr",
            )
            with patch.object(gateway.subprocess, "run", side_effect=timeout_error):
                result = gateway._run_argv(root, ["python3", "demo.py"], timeout=12)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "tool_timeout")
        self.assertEqual(result["timeout_seconds"], 12)
        self.assertEqual(result["returncode"], None)
        self.assertEqual(result["stdout_tail"], "partial stdout")
        self.assertEqual(result["stderr_tail"], "partial stderr")

    def test_smart_run_timeout_does_not_fall_back_to_internal(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                return {
                    "returncode": None,
                    "stdout_tail": "partial stdout",
                    "stderr_tail": "partial stderr",
                    "ok": False,
                    "error": "tool_timeout",
                    "timeout_seconds": timeout,
                    "detail": f"tool timed out after {timeout}s",
                }

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_run", "case_id": "demo"},
                root,
                sys.executable,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "smart_run")
        self.assertEqual(result["result"]["error"], "tool_timeout")
        self.assertNotEqual(result["result"].get("error"), "internal")
        self.assertEqual(result["result"]["timeout_seconds"], 1800)

    def test_smart_refresh_reports_does_not_pass_restrict_flag(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["source_discovery"])
            config_path = self._write_config(root, ["init"])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            calls: list[list[str]] = []

            def fake_run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, object]:
                calls.append(argv)
                return {"returncode": 0, "stdout_tail": "{}", "stderr_tail": "", "ok": True}

            gateway._run_argv = fake_run_argv
            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_refresh_reports", "case_id": "demo"},
                root,
                sys.executable,
            )

            self.assertTrue(result["ok"])
            self.assertNotIn("--restrict-workflow-keys", calls[0])
            self.assertIsNone(result["latest_cli_result"])
            self.assertTrue(result["shared_cli_result_path"].endswith("workflow_smart_cli_result.latest.json"))
            self.assertTrue(result["scoped_cli_result_path"].endswith("workflow_smart_cli_result.refresh_reports.smart.latest.json"))
            self.assertFalse(result["shared_cli_result_exists"])
            self.assertFalse(result["scoped_cli_result_exists"])

    def test_invalid_visible_workflow_config_fails_closed(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["acceptance_review", "release_publish"])
            config_path = root / "agent_visible_workflows.yaml"
            config_path.write_text("allowlist: [", encoding="utf-8")
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            tools, policy = gateway._filter_tools_for_case(root, "demo")
            names = [tool["name"] for tool in tools]

            self.assertIn("case_knowledge_lint", names)
            self.assertNotIn("bootstrap_case_triad_minimal", names)
            self.assertNotIn("smart_plan", names)
            self.assertNotIn("smart_run", names)
            self.assertEqual(policy["agent_visible_workflows"]["source"], "invalid_config")
            self.assertEqual(policy["agent_visible_workflows"]["allowlist"], [])

            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_plan", "case_id": "demo"},
                root,
                sys.executable,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "tool_not_visible_globally")

    def test_empty_allowlist_config_fails_closed(self) -> None:
        gateway = _load_gateway_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_manifest(root, "demo", ["acceptance_review", "release_publish"])
            config_path = self._write_config(root, [])
            gateway.AGENT_VISIBLE_WORKFLOWS_CONFIG = config_path

            tools, policy = gateway._filter_tools_for_case(root, "demo")
            names = [tool["name"] for tool in tools]

            self.assertIn("case_knowledge_lint", names)
            self.assertNotIn("bootstrap_case_triad_minimal", names)
            self.assertNotIn("smart_plan", names)
            self.assertNotIn("smart_run", names)
            self.assertEqual(policy["agent_visible_workflows"]["source"], "empty_allowlist")
            self.assertEqual(policy["agent_visible_workflows"]["allowlist"], [])

            result = gateway._handle(
                {"op": "invoke_tool", "tool": "smart_run", "case_id": "demo"},
                root,
                sys.executable,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "tool_not_visible_globally")


if __name__ == "__main__":
    unittest.main()
