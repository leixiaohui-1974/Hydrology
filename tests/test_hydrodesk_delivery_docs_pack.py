"""hydrodesk_e2e_actions.generate-delivery-docs-pack：快照路径与 dry-run / 缺失案例。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
HYDRO = REPO / "Hydrology"
_SCRIPTS = HYDRO / "scripts"
for p in (HYDRO, REPO, _SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

import workflows.hydrodesk_e2e_actions as hdea  # noqa: E402


class TestHydrodeskDeliveryDocsPack(unittest.TestCase):
    def test_delivery_snapshot_relpaths_non_empty(self) -> None:
        rels = hdea._delivery_snapshot_relpaths()
        self.assertTrue(rels)
        self.assertTrue(all(isinstance(x, str) and x.strip() for x in rels))

    def test_delivery_snapshot_relpaths_include_trio(self) -> None:
        rels = hdea._delivery_snapshot_relpaths()
        for key in [
            "data_assimilation.latest.json",
            "state_estimation.latest.json",
            "parameter_governance.latest.json",
        ]:
            self.assertIn(key, rels)

    def test_subprocess_dry_run_when_daduhe_present(self) -> None:
        contracts = REPO / "cases" / "daduhe" / "contracts"
        if not contracts.is_dir():
            self.skipTest("cases/daduhe/contracts 不存在，跳过子进程 dry-run")
        script = HYDRO / "workflows" / "hydrodesk_e2e_actions.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--case-id", "daduhe", "--action", "generate-delivery-docs-pack", "--delivery-pack-dry-run"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=240,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("action"), "generate-delivery-docs-pack")
        self.assertTrue(payload.get("dry_run"))
        self.assertIn("would_write_snapshots", payload)
        self.assertIn("final_report.latest.json", payload.get("would_write_snapshots", []))
        for key in [
            "data_assimilation.latest.json",
            "state_estimation.latest.json",
            "parameter_governance.latest.json",
        ]:
            self.assertIn(key, payload.get("would_write_snapshots", []))
    def test_release_pack_artifacts_include_trio_mapping(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hydrodesk_release_pack_test_") as temp_dir:
            case_id = "tmpcase"
            contracts = Path(temp_dir) / "cases" / case_id / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            for filename in [
                "data_assimilation.latest.json",
                "state_estimation.latest.json",
                "parameter_governance.latest.json",
            ]:
                (contracts / filename).write_text("{}", encoding="utf-8")

            artifacts = hdea._optional_trio_release_artifacts(case_id, contracts)
            self.assertEqual(
                artifacts,
                {
                    "data_assimilation": f"cases/{case_id}/contracts/data_assimilation.latest.json",
                    "state_estimation": f"cases/{case_id}/contracts/state_estimation.latest.json",
                    "parameter_governance": f"cases/{case_id}/contracts/parameter_governance.latest.json",
                },
            )

    def test_release_pack_artifacts_omit_missing_trio_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hydrodesk_release_pack_test_missing_") as temp_dir:
            case_id = "tmpcase_missing"
            contracts = Path(temp_dir) / "cases" / case_id / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            (contracts / "state_estimation.latest.json").write_text("{}", encoding="utf-8")

            artifacts = hdea._optional_trio_release_artifacts(case_id, contracts)
            self.assertEqual(
                artifacts,
                {
                    "state_estimation": f"cases/{case_id}/contracts/state_estimation.latest.json",
                },
            )

    def test_build_release_pack_omits_missing_trio_in_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hydrodesk_release_pack_integration_") as temp_dir:
            temp_root = Path(temp_dir)
            case_id = "tmpcase_integration"
            contracts = temp_root / "cases" / case_id / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)

            progress_payload = {
                "run_id": "tmp-run",
                "records": [],
                "summary": {},
            }
            (contracts / "e2e_live_progress.latest.json").write_text(
                json.dumps(progress_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            (contracts / "state_estimation.latest.json").write_text("{}", encoding="utf-8")

            release_manifest_cli_holder: dict[str, list[str]] = {}

            def _stub_run_python_script(script_rel: str, args: list[str]) -> dict[str, object]:
                if script_rel.endswith("build_release_manifest.py"):
                    release_manifest_cli_holder["args"] = list(args)
                return {
                    "command": [sys.executable, script_rel, *args],
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                }

            with (
                patch.object(hdea, "WORKSPACE", temp_root),
                patch.object(hdea, "_run_python_script", side_effect=_stub_run_python_script),
                patch.object(hdea, "action_refresh_dashboard", return_value={"action": "refresh-dashboard"}),
            ):
                payload = hdea.action_build_release_pack(case_id)

            self.assertTrue(payload.get("ok"), payload)

            pack_path = temp_root / payload["release_pack"]
            self.assertTrue(pack_path.is_file(), payload)
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            artifacts = pack.get("artifacts", {})

            self.assertIn("state_estimation", artifacts)
            self.assertNotIn("data_assimilation", artifacts)
            self.assertNotIn("parameter_governance", artifacts)
            self.assertEqual(
                artifacts.get("final_report"),
                f"cases/{case_id}/contracts/final_report.latest.json",
            )
            self.assertEqual(
                artifacts.get("state_estimation"),
                f"cases/{case_id}/contracts/state_estimation.latest.json",
            )

            manifest_args = release_manifest_cli_holder.get("args", [])
            self.assertTrue(manifest_args, "未捕获到 build_release_manifest.py 调用参数")
            artifact_values = [
                manifest_args[i + 1]
                for i, value in enumerate(manifest_args[:-1])
                if value == "--artifact"
            ]
            self.assertIn(f"cases/{case_id}/contracts/state_estimation.latest.json", artifact_values)
            self.assertNotIn(f"cases/{case_id}/contracts/data_assimilation.latest.json", artifact_values)
            self.assertNotIn(f"cases/{case_id}/contracts/parameter_governance.latest.json", artifact_values)
            self.assertIn("final_report", pack.get("calls", {}))


if __name__ == "__main__":
    unittest.main()
