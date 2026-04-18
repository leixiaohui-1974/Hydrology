from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
import tempfile

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from workflows._shared import load_case_config
import workflows._shared as shared


def _assert_no_workspace_absolute_paths(value: object, workspace_root: str | Path | None = None) -> None:
    root = Path(workspace_root).resolve() if workspace_root is not None else BASE_DIR.parent.resolve()

    def _walk(item: object) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                _walk(nested)
            return
        if isinstance(item, (list, tuple)):
            for nested in item:
                _walk(nested)
            return
        if isinstance(item, str):
            text = item.strip()
            if text.startswith("[external]/"):
                return
            if Path(text).is_absolute():
                raise AssertionError(f"unexpected absolute path: {item}")
            assert str(root) not in item, f"unexpected workspace absolute path: {item}"

    _walk(value)


def _load_nl_gateway_module():
    module_path = BASE_DIR / "workflows" / "nl_mcp_gateway.py"
    spec = importlib.util.spec_from_file_location("nl_mcp_gateway_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _import_hydrodesk_loop_yaml_util():
    scripts = BASE_DIR / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import hydrodesk_loop_yaml_util as util

    return util


class CaseConfigAndGatewayRegressionTests(unittest.TestCase):
    def test_load_case_config_yjdt_without_recursive_knowledge_fallback(self):
        cfg = load_case_config("yjdt")

        self.assertEqual(cfg["case_id"], "yjdt")
        self.assertEqual(cfg["project_type"], "cascade_hydro")
        self.assertTrue(cfg["yjdt_params_source"].endswith("YJDT/src/yjdt/config/yajiang_bigbend_params.yaml"))
        self.assertTrue(Path(cfg["yjdt_params_source"]).is_absolute())

    def test_resolve_case_entry_inputs_falls_back_to_existing_data_pack_pointers(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_id = "generic_case"
            manifest_path = root / "cases" / case_id / "manifest.yaml"
            contracts_dir = manifest_path.parent / "contracts"
            contracts_dir.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text("case:\n  id: generic_case\n", encoding="utf-8")
            source_bundle = contracts_dir / "source_bundle.contract.json"
            outlets = contracts_dir / "outlets.normalized.json"
            source_bundle.write_text("{}", encoding="utf-8")
            outlets.write_text("{}", encoding="utf-8")
            (contracts_dir / "data_pack.latest.json").write_text(
                json.dumps(
                    {
                        "source_bundle_json": str(source_bundle),
                        "outlets_json": str(outlets),
                    }
                ),
                encoding="utf-8",
            )

            orig_workspace = shared.WORKSPACE
            orig_base = shared.BASE_DIR
            try:
                shared.WORKSPACE = root
                shared.BASE_DIR = root / "Hydrology"
                resolved = shared.resolve_case_entry_inputs(case_id, case_manifest=str(manifest_path))
            finally:
                shared.WORKSPACE = orig_workspace
                shared.BASE_DIR = orig_base

            self.assertEqual(resolved["case_manifest"], f"cases/{case_id}/manifest.yaml")
            self.assertEqual(resolved["source_bundle_json"], f"cases/{case_id}/contracts/source_bundle.contract.json")
            self.assertEqual(resolved["outlets_json"], f"cases/{case_id}/contracts/outlets.normalized.json")
            _assert_no_workspace_absolute_paths(resolved, root)

    def test_resolve_case_entry_inputs_uses_data_pack_when_manifest_and_config_are_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_id = "generic_case"
            manifest_path = root / "cases" / case_id / "manifest.yaml"
            contracts_dir = manifest_path.parent / "contracts"
            contracts_dir.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text("case:\n  id: generic_case\n", encoding="utf-8")
            source_bundle = contracts_dir / "source_bundle.contract.json"
            outlets = contracts_dir / "outlets.normalized.json"
            source_bundle.write_text("{}", encoding="utf-8")
            outlets.write_text("{}", encoding="utf-8")
            (contracts_dir / "data_pack.latest.json").write_text(
                json.dumps(
                    {
                        "source_bundle_json": f"cases/{case_id}/contracts/source_bundle.contract.json",
                        "outlets_json": f"cases/{case_id}/contracts/outlets.normalized.json",
                    }
                ),
                encoding="utf-8",
            )

            orig_workspace = shared.WORKSPACE
            orig_base = shared.BASE_DIR
            orig_load_case_config = shared.load_case_config
            try:
                shared.WORKSPACE = root
                shared.BASE_DIR = root / "Hydrology"
                shared.load_case_config = lambda _case_id, config_path=None: {"case_id": _case_id}
                resolved = shared.resolve_case_entry_inputs(case_id, case_manifest=str(manifest_path))
            finally:
                shared.WORKSPACE = orig_workspace
                shared.BASE_DIR = orig_base
                shared.load_case_config = orig_load_case_config

            self.assertEqual(resolved["case_manifest"], f"cases/{case_id}/manifest.yaml")
            self.assertEqual(resolved["source_bundle_json"], f"cases/{case_id}/contracts/source_bundle.contract.json")
            self.assertEqual(resolved["outlets_json"], f"cases/{case_id}/contracts/outlets.normalized.json")
            _assert_no_workspace_absolute_paths(resolved, root)

    def test_load_case_manifest_falls_back_to_json_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_id = "generic_case"
            contracts_dir = root / "cases" / case_id / "contracts"
            contracts_dir.mkdir(parents=True, exist_ok=True)
            fallback = contracts_dir / "case_manifest.json"
            fallback.write_text(json.dumps({"case": {"id": case_id}}), encoding="utf-8")

            orig_workspace = shared.WORKSPACE
            try:
                shared.WORKSPACE = root
                resolved_path, payload = shared.load_case_manifest(case_id)
            finally:
                shared.WORKSPACE = orig_workspace

            self.assertEqual(resolved_path, fallback.resolve())
            self.assertEqual(payload, {"case": {"id": case_id}})

    def test_load_case_manifest_bad_json_fallback_returns_empty_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            case_id = "generic_case"
            contracts_dir = root / "cases" / case_id / "contracts"
            contracts_dir.mkdir(parents=True, exist_ok=True)
            fallback = contracts_dir / "case_manifest.json"
            fallback.write_text("{broken", encoding="utf-8")

            orig_workspace = shared.WORKSPACE
            try:
                shared.WORKSPACE = root
                resolved_path, payload = shared.load_case_manifest(case_id)
            finally:
                shared.WORKSPACE = orig_workspace

            self.assertEqual(resolved_path, fallback.resolve())
            self.assertEqual(payload, {})

    def test_nl_gateway_uses_daduhe_yaml_topology_graph(self):
        gateway = _load_nl_gateway_module()

        response = gateway.mcp_agent_routing("check daduhe topology")
        entities = response["report"]["entities"]

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["case_id"], "daduhe")
        self.assertGreater(len(entities), 5)
        self.assertTrue(any(entity["id"].startswith("daduhe_node_") for entity in entities))
        self.assertTrue(all(entity["id"] != "daduhe_res_01" for entity in entities))

    def test_print_hydrodesk_topology_live_writes_marked_json_to_stderr(self):
        """HydroDesk Tauri 从 stderr 解析拓扑块；stdout 留给单行主 JSON。"""
        gateway = _load_nl_gateway_module()
        buf = io.StringIO()
        old_err = sys.stderr
        try:
            sys.stderr = buf
            gateway.print_hydrodesk_topology_live(
                [{"id": "n1", "type": "reach", "label": "r1"}],
                [{"id": "e1", "source": "n0", "target": "n1", "label": "in"}],
                "merge",
            )
        finally:
            sys.stderr = old_err
        s = buf.getvalue()
        self.assertIn("<<<HYDRODESK_TOPOLOGY_JSON\n", s)
        self.assertIn("\n>>>HYDRODESK_TOPOLOGY_JSON", s)
        start = s.index("<<<HYDRODESK_TOPOLOGY_JSON\n") + len("<<<HYDRODESK_TOPOLOGY_JSON\n")
        end = s.index("\n>>>HYDRODESK_TOPOLOGY_JSON")
        payload = json.loads(s[start:end])
        self.assertEqual(payload["mode"], "merge")
        self.assertEqual(len(payload["entities"]), 1)
        self.assertEqual(len(payload["edges"]), 1)
        self.assertEqual(payload["entities"][0]["id"], "n1")

    def test_nl_gateway_resolve_case_id_chinese_aliases(self):
        gateway = _load_nl_gateway_module()
        self.assertEqual(gateway._resolve_case_id_from_query("雅江流域拓扑"), "yjdt")
        self.assertEqual(gateway._resolve_case_id_from_query("雅鲁藏布 模型"), "yjdt")
        self.assertEqual(gateway._resolve_case_id_from_query("徐洪河 水文"), "xuhonghe")
        self.assertEqual(gateway._resolve_case_id_from_query("中线 干线调度"), "zhongxian")

    def test_yjdt_pipedream_control_yaml_exists(self):
        gateway = _load_nl_gateway_module()
        path = gateway._pipedream_case_yaml_path("yjdt")
        self.assertTrue(path.is_file(), msg=f"expected Pipedream case yaml: {path}")

    def test_gateway_control_profile_yjdt_cascade(self):
        gateway = _load_nl_gateway_module()
        cfg = gateway._load_pipedream_case_config("yjdt")
        self.assertTrue(cfg)
        self.assertEqual(gateway._infer_gateway_control_profile(cfg), "cascade_reservoir")
        k = gateway._extract_e2e_kernel_params(cfg, "yjdt")
        self.assertEqual(k["profile"], "cascade_reservoir")
        self.assertEqual(k["reservoir_name"], "雅江派墨站")
        self.assertEqual(k["max_discharge"], 5000.0)

    def test_gateway_control_profile_zhongxian_canal(self):
        gateway = _load_nl_gateway_module()
        cfg = gateway._load_pipedream_case_config("zhongxian")
        self.assertTrue(cfg)
        self.assertEqual(gateway._infer_gateway_control_profile(cfg), "canal_actuators")
        k = gateway._extract_e2e_kernel_params(cfg, "zhongxian")
        self.assertEqual(k["profile"], "canal_actuators")
        self.assertAlmostEqual(k["initial_level"], 165.88)
        self.assertEqual(k["reservoir_name"], "中线总干渠主控闸")
        self.assertEqual(k["max_discharge"], 350.0)
        self.assertGreater(k["z_max"], k["z_min"])

    def test_canal_cases_define_primary_actuators_at_design_flow(self):
        case_dir = (
            BASE_DIR.parent
            / "pipedream-hydrology-integration-lab"
            / "hydromind_control_server"
            / "configs"
            / "cases"
        )
        expectations = {
            "yinchuo": ("gate", 14.61),
            "jiaodong": ("gate", 15.0),
            "xuhonghe": ("pump", 50.0),
            "zhongxian": ("gate", 350.0),
        }
        for case_id, (kind, design_flow) in expectations.items():
            cfg = yaml.safe_load((case_dir / f"{case_id}.yaml").read_text(encoding="utf-8"))
            actuators = cfg["model"]["actuators"]
            self.assertEqual(len(actuators), 1)
            self.assertEqual(actuators[0]["type"], kind)
            self.assertEqual(float(actuators[0]["max_flow_m3s"]), design_flow)
            self.assertEqual(float(cfg["model"]["hydraulics"]["design_flow_m3s"]), design_flow)

    def test_gateway_topology_loads_for_all_rollout_control_slugs(self):
        gateway = _load_nl_gateway_module()
        for case_id in ("yinchuo", "jiaodong", "xuhonghe", "zhongxian", "yjdt"):
            response = gateway.mcp_agent_routing(f"check {case_id} topology")
            self.assertEqual(response["status"], "success")
            self.assertEqual(response["case_id"], case_id)
            self.assertGreater(len(response["report"]["entities"]), 0)

    def test_gateway_control_assets_alias_merges_with_actuators(self):
        gateway = _load_nl_gateway_module()
        cfg = {
            "meta": {"id": "fixture", "type": "canal"},
            "model": {
                "reservoirs": [],
                "control_assets": [{"id": "g1", "type": "gate", "max_flow_m3s": 12.0}],
            },
        }
        self.assertEqual(gateway._infer_gateway_control_profile(cfg), "canal_actuators")
        k = gateway._extract_e2e_kernel_params(cfg, "fixture")
        self.assertEqual(k["profile"], "canal_actuators")
        self.assertGreaterEqual(k["max_discharge"], 12.0)

    def test_legacy_hydrodesk_six_case_loop_yaml_redirects(self):
        path = BASE_DIR / "configs" / "hydrodesk_six_case_e2e_loop.yaml"
        self.assertTrue(path.is_file(), msg=f"missing loop config: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(
            raw.get("redirect_config"),
            "Hydrology/configs/hydrodesk_autonomous_waternet_e2e_loop.yaml",
        )

    def test_autonomous_waternet_loop_config_shape(self):
        path = BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
        self.assertTrue(path.is_file(), msg=f"missing autonomous loop config: {path}")
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("platform", {}).get("id"), "autonomous_water_network_modeling_agent")
        sel = cfg.get("case_selection") or {}
        self.assertEqual(sel.get("mode"), "explicit")
        self.assertEqual(
            sel.get("case_ids"),
            [
                "zhongxian",
                "xuhonghe",
                "yinchuojiliao",
                "jiaodongtiaoshui",
                "daduhe",
                "yjdt",
            ],
        )
        stages = cfg.get("stages") or []
        first = stages[0] if stages else {}
        self.assertEqual(first.get("pipeline_phase"), "watershed")
        self.assertTrue(first.get("respect_stage_guidance"))
        actions = [s.get("action") for s in stages if isinstance(s, dict) and s.get("action")]
        self.assertEqual(
            actions,
            [
                "refresh-dashboard",
                "run-fast",
                "run-full-review",
                "run-scada-replay",
                "build-release-pack",
            ],
        )
        scada = next(
            (s for s in stages if isinstance(s, dict) and s.get("id") == "scada_replay"),
            None,
        )
        self.assertIsNotNone(scada)
        self.assertEqual(scada.get("action"), "run-scada-replay")
        self.assertTrue(scada.get("skip_if_sqlite_missing"))
        self.assertTrue(str(cfg.get("hydrodesk_e2e_script", "")).endswith("hydrodesk_e2e_actions.py"))
        self.assertTrue(str(cfg.get("case_pipeline_script", "")).endswith("run_case_pipeline.py"))
        dims = (cfg.get("quality_loop") or {}).get("dimensions") or []
        self.assertGreaterEqual(len(dims), 10)

    def test_hydrodesk_loop_scada_sqlite_path_fn_matches_resolve_config(self):
        """编排器跳过逻辑与 hydrodesk_e2e_actions 使用同一 SQLite 路径约定。"""
        loop_py = BASE_DIR / "scripts" / "run_hydrodesk_six_case_e2e_loop.py"
        spec = importlib.util.spec_from_file_location("hd_six_loop_under_test", loop_py)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        from workflows.hydrodesk_e2e_actions import resolve_scada_replay_config

        case_id = "nonexistent_case_for_sqlite_path_probe"
        p_loop = mod._scada_sqlite_path_for_skip(case_id)
        _qs, _qe, p_cfg, _sid = resolve_scada_replay_config(case_id)
        self.assertEqual(p_loop.resolve(), p_cfg.resolve())
        self.assertTrue(str(p_loop).endswith(f"{case_id}_hydromind.sqlite3"), p_loop)

    def test_load_loop_config_follows_redirect(self):
        util = _import_hydrodesk_loop_yaml_util()
        ws = BASE_DIR.parent
        cfg = util.load_loop_yaml(ws, BASE_DIR / "configs" / "hydrodesk_six_case_e2e_loop.yaml")
        self.assertEqual(cfg.get("platform", {}).get("id"), "autonomous_water_network_modeling_agent")

    def test_check_rollout_cases_loadable_requires_entry_complete_cases(self):
        script = BASE_DIR / "scripts" / "check_rollout_cases_loadable.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        self.assertIn("entry-complete", proc.stdout)

    def test_check_rollout_cases_loadable_can_repair_missing_entry_files(self):
        scripts = str(BASE_DIR / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import check_rollout_cases_loadable as target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case_root = root / "cases" / "demo_case"
            contracts = case_root / "contracts"
            contracts.mkdir(parents=True, exist_ok=True)
            hydrology_root = root / "Hydrology" / "configs"
            hydrology_root.mkdir(parents=True, exist_ok=True)
            (hydrology_root / "demo_case.yaml").write_text(
                "case_id: demo_case\ndisplay_name: 演示案例\nproject_type: canal\n",
                encoding="utf-8",
            )
            broken_manifest = case_root / "manifest.yaml"
            broken_manifest.symlink_to(broken_manifest)
            broken_links = case_root / "links.yaml"
            broken_links.symlink_to(broken_links)
            broken_case_manifest = contracts / "case_manifest.json"
            broken_case_manifest.symlink_to(broken_case_manifest)

            orig_workspace = target.WORKSPACE
            orig_hydrology_root = target.HYDROLOGY_ROOT
            orig_git_head = target._git_head_file_text
            try:
                target.WORKSPACE = root
                target.HYDROLOGY_ROOT = root / "Hydrology"
                target._git_head_file_text = lambda relpath: None
                repaired = target._repair_case_entry_files(
                    "demo_case",
                    display_name="演示案例",
                    project_type="canal",
                )
            finally:
                target.WORKSPACE = orig_workspace
                target.HYDROLOGY_ROOT = orig_hydrology_root
                target._git_head_file_text = orig_git_head

            self.assertIn("cases/demo_case/manifest.yaml", repaired)
            self.assertIn("cases/demo_case/links.yaml", repaired)
            self.assertIn("cases/demo_case/contracts/case_manifest.json", repaired)
            self.assertTrue((case_root / "manifest.yaml").is_file())
            self.assertTrue((case_root / "links.yaml").is_file())
            self.assertTrue((contracts / "case_manifest.json").is_file())

    def test_resolve_case_ids_manifest_glob(self):
        util = _import_hydrodesk_loop_yaml_util()
        ws = BASE_DIR.parent
        ids = util.resolve_case_ids(
            {"case_selection": {"mode": "manifest_glob", "manifest_glob": "cases/*/manifest.yaml"}},
            ws,
        )
        self.assertGreaterEqual(len(ids), 5)
        for cid in ("yjdt", "zhongxian"):
            self.assertIn(cid, ids)

    def test_hydrodesk_six_case_loop_ids_match_case_manifests(self):
        root = BASE_DIR.parent / "cases"
        util = _import_hydrodesk_loop_yaml_util()
        ws = BASE_DIR.parent
        cfg = util.load_loop_yaml(ws, BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml")
        for cid in util.resolve_case_ids(cfg, ws):
            mf = root / cid / "manifest.yaml"
            fallback = root / cid / "contracts" / "case_manifest.json"
            workflow_run = root / cid / "contracts" / "workflow_run.json"
            self.assertTrue(
                mf.is_file() or fallback.is_file() or workflow_run.is_file(),
                msg=f"expected manifest-like entry for cases/{cid}",
            )

    def test_export_autonomous_waternet_quality_rubric_stdout_json(self):
        script = BASE_DIR / "scripts" / "export_autonomous_waternet_quality_rubric.py"
        self.assertTrue(script.is_file(), msg=f"missing {script}")
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        line = (proc.stdout or "").strip().split("\n", 1)[0]
        data = json.loads(line)
        self.assertEqual(data.get("platform", {}).get("id"), "autonomous_water_network_modeling_agent")
        dims = (data.get("quality_loop") or {}).get("dimensions") or []
        self.assertGreaterEqual(len(dims), 10)

    def test_export_quality_rubric_follows_six_case_yaml_redirect(self):
        script = BASE_DIR / "scripts" / "export_autonomous_waternet_quality_rubric.py"
        legacy = BASE_DIR / "configs" / "hydrodesk_six_case_e2e_loop.yaml"
        proc = subprocess.run(
            [sys.executable, str(script), "--config", str(legacy)],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        data = json.loads((proc.stdout or "").strip().split("\n", 1)[0])
        self.assertGreaterEqual(len((data.get("quality_loop") or {}).get("dimensions") or []), 10)

    def test_check_case_quality_artifacts_daduhe(self):
        script = BASE_DIR / "scripts" / "check_case_quality_artifacts.py"
        self.assertTrue(script.is_file())
        proc = subprocess.run(
            [sys.executable, str(script), "--case-id", "daduhe"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        data = json.loads((proc.stdout or "").strip().split("\n", 1)[0])
        self.assertEqual(data.get("case_id"), "daduhe")
        summary = data.get("summary") or {}
        self.assertGreater(summary.get("dimensions_total", 0), 0)
        self.assertGreaterEqual(summary.get("dimensions_satisfied", 0), 1)
        self.assertIn("workflow_outputs_count", summary)
        self.assertIn("workflow_outputs_ready", summary)
        self.assertIn("data_pack_basin_validation_present", summary)
        self.assertIn("source_bundle_present", summary)
        self.assertIn("source_import_session_present", summary)
        self.assertIn("source_import_mode", summary)
        self.assertIn("source_imported_at", summary)
        self.assertIn("pipeline_contract_ready", summary)
        self.assertIn("source_import_session", data)
        self.assertIn("present", data["source_import_session"])

    def test_check_case_quality_artifacts_batch_matches_current_rollout(self):
        script = BASE_DIR / "scripts" / "check_case_quality_artifacts.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--batch"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        data = json.loads((proc.stdout or "").strip().split("\n", 1)[0])
        self.assertTrue(data.get("batch"))
        self.assertEqual(len(data.get("case_ids") or []), 6)
        rollup = data.get("rollup") or {}
        self.assertEqual(rollup.get("case_count"), 6)
        self.assertGreaterEqual(rollup.get("cases_with_contracts_dir", 0), 1)
        per = rollup.get("per_case") or []
        self.assertEqual(len(per), 6)
        for row in per:
            self.assertIn("workflow_outputs_count", row)
            self.assertIn("workflow_outputs_ready", row)
            self.assertIn("data_pack_basin_validation_present", row)
            self.assertIn("source_bundle_present", row)
            self.assertIn("source_import_session_present", row)
            self.assertIn("source_import_mode", row)
            self.assertIn("source_imported_at", row)
            self.assertIn("pipeline_contract_ready", row)

    def test_check_case_quality_artifacts_requires_case_or_batch(self):
        script = BASE_DIR / "scripts" / "check_case_quality_artifacts.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_scaffold_new_case_dry_run(self):
        script = BASE_DIR / "scripts" / "scaffold_new_case.py"
        self.assertTrue(script.is_file())
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--case-id",
                "fixture_scaffold_dry",
                "--display-name",
                "DryFixture",
                "--dry-run",
            ],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip())
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("status"), "dry_run")

    def test_scaffold_new_case_invalid_id(self):
        script = BASE_DIR / "scripts" / "scaffold_new_case.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--case-id",
                "Bad-Id",
                "--display-name",
                "x",
            ],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 2)
        err = json.loads(proc.stderr.strip())
        self.assertFalse(err.get("ok"))

    def test_scaffold_register_loop_config_appends_once(self):
        import shutil
        import tempfile

        scripts = str(BASE_DIR / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from scaffold_new_case import register_case_in_loop_config

        src = BASE_DIR / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "loop.yaml"
            shutil.copy(src, p)
            tag = "__register_test_tag__"
            self.assertTrue(register_case_in_loop_config(tag, p))
            self.assertFalse(register_case_in_loop_config(tag, p))
            cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
            ids = (cfg.get("case_selection") or {}).get("case_ids") or []
            self.assertIn(tag, ids)

    def test_export_case_workflow_feasibility_daduhe(self):
        script = BASE_DIR / "scripts" / "export_case_workflow_feasibility.py"
        self.assertTrue(script.is_file())
        proc = subprocess.run(
            [sys.executable, str(script), "--case-id", "daduhe"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip())
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("case_id"), "daduhe")
        self.assertIn("signals", data)
        self.assertTrue(data["signals"].get("case_config_file"))
        self.assertIn("source_import_session_file", data["signals"])
        self.assertIn("source_import_session", data)
        self.assertIn("present", data["source_import_session"])
        self.assertIn("source", data["source_import_session"])
        wfs = data.get("workflows") or []
        self.assertGreater(len(wfs), 10)
        keys = {w["key"] for w in wfs}
        self.assertIn("model", keys)
        model_row = next(w for w in wfs if w["key"] == "model")
        self.assertIn(model_row["tier"], ("data_ok", "data_gap", "registry_only", "no_case_config"))

    def test_export_case_workflow_feasibility_no_case_yaml(self):
        script = BASE_DIR / "scripts" / "export_case_workflow_feasibility.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--case-id", "__no_such_case_xyz__"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip())
        self.assertTrue(data.get("ok"))
        self.assertFalse(data["signals"]["case_config_file"])
        self.assertFalse(data["signals"]["source_import_session_file"])
        for w in data["workflows"]:
            self.assertEqual(w["tier"], "no_case_config")

    def test_export_case_workflow_feasibility_tightens_hyd_cal_and_calibrate_to_runtime_ready_signals(self):
        script = BASE_DIR / "scripts" / "export_case_workflow_feasibility.py"

        def _export(case_id: str) -> dict:
            proc = subprocess.run(
                [sys.executable, str(script), "--case-id", case_id],
                cwd=str(BASE_DIR.parent),
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout.strip())
            self.assertTrue(payload.get("ok"))
            return payload

        daduhe = _export("daduhe")
        daduhe_signals = daduhe["signals"]
        self.assertTrue(daduhe_signals["supported_sqlite_files"])
        self.assertTrue(daduhe_signals["candidate_station_meta"])
        self.assertTrue(daduhe_signals["hydraulic_station_series_ready"])
        self.assertTrue(daduhe_signals["report_pairable_series_ready"])
        daduhe_rows = {row["key"]: row for row in daduhe["workflows"]}
        self.assertEqual(daduhe_rows["hyd_cal"]["tier"], "data_ok")
        self.assertEqual(daduhe_rows["calibrate"]["tier"], "data_ok")

        for case_id in ("xuhonghe", "jiaodongtiaoshui", "zhongxian"):
            payload = _export(case_id)
            rows = {row["key"]: row for row in payload["workflows"]}
            signals = payload["signals"]
            self.assertFalse(signals["hydraulic_station_series_ready"], msg=case_id)
            self.assertEqual(rows["hyd_cal"]["tier"], "data_gap", msg=case_id)
            self.assertEqual(rows["calibrate"]["tier"], "data_gap", msg=case_id)

        yinchuojiliao = _export("yinchuojiliao")
        yin_rows = {row["key"]: row for row in yinchuojiliao["workflows"]}
        yin_signals = yinchuojiliao["signals"]
        self.assertTrue(yin_signals["supported_sqlite_files"])
        self.assertTrue(yin_signals["report_pairable_series_ready"])
        self.assertFalse(yin_signals["hydraulic_station_series_ready"])
        self.assertEqual(yin_rows["hyd_cal"]["tier"], "data_gap")
        self.assertEqual(yin_rows["calibrate"]["tier"], "data_ok")

    def test_export_case_platform_readiness_merged_daduhe(self):
        script = BASE_DIR / "scripts" / "export_case_platform_readiness.py"
        self.assertTrue(script.is_file())
        proc = subprocess.run(
            [sys.executable, str(script), "--case-id", "daduhe"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip())
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("case_id"), "daduhe")
        self.assertIn("platform_rubric", data)
        self.assertIn("artifact_coverage", data)
        self.assertIn("workflow_feasibility", data)
        self.assertIn("summary", data)
        self.assertIn("quality_loop", data["platform_rubric"])
        self.assertIn("workflows", data["workflow_feasibility"])
        summary = data.get("summary") or {}
        self.assertIn("workflow_outputs_count", summary)
        self.assertIn("workflow_outputs_ready", summary)
        self.assertIn("data_pack_basin_validation_present", summary)
        self.assertIn("source_bundle_present", summary)
        self.assertIn("pipeline_contract_ready", summary)
        self.assertIn("entry_case_manifest_source", summary)
        self.assertIn("entry_source_bundle_source", summary)
        self.assertIn("entry_outlets_source", summary)
        self.assertIn("entry_simulation_config_source", summary)
        self.assertIn("entry_source_import_session_source", summary)
        self.assertIn("source_import_session_present", summary)
        self.assertIn("source_import_session_path", summary)
        self.assertIn("source_import_mode", summary)
        self.assertIn("source_import_record_count", summary)
        self.assertIn("source_imported_at", summary)
        self.assertIn("graphify_sidecar_status", summary)
        self.assertIn("graphify_supports_auto_modeling_hints", summary)
        self.assertIn("graphify_modeling_signal_counts", summary)
        self.assertIn("entry_inputs", data)
        self.assertIn("source_import_session", data)
        self.assertIn("source", data["source_import_session"])
        self.assertIn("path", data["source_import_session"])
        self.assertIn("payload", data["source_import_session"])
        self.assertIn("graphify_sidecar", data)
        _assert_no_workspace_absolute_paths(data["entry_inputs"])
        _assert_no_workspace_absolute_paths(data["source_import_session"])
        _assert_no_workspace_absolute_paths(data["graphify_sidecar"])

    def test_run_workflow_baseline_help_mentions_real_script_name(self):
        script = BASE_DIR / "examples" / "run_workflow_baseline.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        out = proc.stdout
        self.assertIn("run_workflow_baseline.py", out)
        self.assertNotIn("map_workflow_baseline.py", out)

    def test_six_case_loop_dry_run_json_summary_contains_skip_reason_shape(self):
        script = BASE_DIR / "scripts" / "run_hydrodesk_six_case_e2e_loop.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--dry-run", "--json-summary", "--case-id", "zhongxian"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertIn("ok", data)
        self.assertIn("summary", data)
        self.assertIn("preflight_report", data)
        self.assertIn("modeling_hints", data["preflight_report"])
        self.assertIn("source_import_sessions", data["preflight_report"])
        self.assertIn("zhongxian", data["preflight_report"]["modeling_hints"])
        self.assertIn("zhongxian", data["preflight_report"]["source_import_sessions"])
        self.assertIsInstance(data["summary"], list)
        for row in data["summary"]:
            if row.get("skipped"):
                self.assertIn("skip_reason", row)
                self.assertTrue(str(row["skip_reason"]).startswith("missing_inputs:"))

    def test_six_case_loop_dry_run_case_pipeline_uses_case_id_driven_command_shape(self):
        script = BASE_DIR / "scripts" / "run_hydrodesk_six_case_e2e_loop.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--dry-run", "--json-summary", "--case-id", "daduhe"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        case_pipeline_rows = [
            row for row in data["summary"]
            if row.get("runner") == "case_pipeline"
        ]
        self.assertTrue(case_pipeline_rows, "expected at least one case_pipeline dry-run row")
        row = case_pipeline_rows[0]
        self.assertIn("preflight_report", data)
        hints = (data.get("preflight_report") or {}).get("modeling_hints", {}).get("daduhe")
        source_import = (data.get("preflight_report") or {}).get("source_import_sessions", {}).get("daduhe")
        self.assertIsInstance(hints, dict)
        self.assertIsInstance(source_import, dict)
        self.assertIn("suggested_workflows", hints)
        self.assertIn("graphify_supports_auto_modeling_hints", hints)
        self.assertIn("present", source_import)
        self.assertIn("source", source_import)
        self.assertIn("path", source_import)
        if row.get("skipped"):
            self.assertTrue(str(row.get("skip_reason", "")).startswith("missing_inputs:"))
            self.assertIn("daduhe", (data.get("preflight_report") or {}).get("missing_inputs", {}))
            self.assertEqual(row.get("modeling_hints"), hints)
            self.assertEqual(row.get("source_import_session"), source_import)
        else:
            command = row.get("command", "")
            self.assertIn("--case-id daduhe", command)
            self.assertIn("--phase watershed", command)
            self.assertIn("--respect-stage-guidance", command)
            self.assertNotIn("--case-manifest", command)
            self.assertNotIn("--source-bundle-json", command)
            self.assertNotIn("--outlets-json", command)
            self.assertEqual(row.get("modeling_hints"), hints)
            self.assertEqual(row.get("source_import_session"), source_import)

    def test_rollout_loop_alias_script_list_cases_matches_legacy_entry(self):
        legacy = BASE_DIR / "scripts" / "run_hydrodesk_six_case_e2e_loop.py"
        alias = BASE_DIR / "scripts" / "run_hydrodesk_rollout_e2e_loop.py"
        self.assertTrue(alias.is_file(), msg=f"missing rollout alias: {alias}")
        legacy_proc = subprocess.run(
            [sys.executable, str(legacy), "--list-cases"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        alias_proc = subprocess.run(
            [sys.executable, str(alias), "--list-cases"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(legacy_proc.returncode, 0, msg=legacy_proc.stderr)
        self.assertEqual(alias_proc.returncode, 0, msg=alias_proc.stderr)
        self.assertEqual(
            json.loads(legacy_proc.stdout.strip()),
            json.loads(alias_proc.stdout.strip()),
        )

    def test_rollout_loop_can_propagate_respect_stage_guidance_flag(self):
        script = BASE_DIR / "scripts" / "run_hydrodesk_six_case_e2e_loop.py"
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "loop.yaml"
            cfg_path.write_text(
                yaml.safe_dump(
                    {
                        "case_selection": {"mode": "explicit", "case_ids": ["daduhe"]},
                        "case_pipeline_script": "Hydrology/workflows/run_case_pipeline.py",
                        "stages": [
                            {
                                "id": "case_pipeline_simulation",
                                "pipeline_phase": "simulation",
                                "respect_stage_guidance": True,
                                "continue_on_error": True,
                            }
                        ],
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, str(script), "--dry-run", "--json-summary", "--config", str(cfg_path)],
                cwd=str(BASE_DIR.parent),
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        row = next(item for item in data["summary"] if item.get("runner") == "case_pipeline")
        self.assertTrue(row.get("respect_stage_guidance"))
        self.assertIn("--respect-stage-guidance", row.get("command", ""))

    def test_export_rollout_readiness_baseline_includes_import_chain_rollup(self):
        script = BASE_DIR / "scripts" / "export_rollout_readiness_baseline.py"
        self.assertTrue(script.is_file())
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "rollout_readiness_baseline.json"
            proc = subprocess.run(
                [sys.executable, str(script), "--output", str(output)],
                cwd=str(BASE_DIR.parent),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload.get("ok"))
            rollup = payload.get("import_chain_rollup") or {}
            self.assertEqual(rollup.get("case_count"), len(payload.get("case_ids") or []))
            self.assertIn("imported_case_count", rollup)
            self.assertIn("missing_case_count", rollup)
            self.assertIn("coverage_ratio", rollup)
            self.assertIn("ready", rollup)
            self.assertIn("status", rollup)
            self.assertIn("reason", rollup)
            self.assertIn("ready_case_ids", rollup)
            self.assertIn("missing_case_ids", rollup)
            self.assertIn("per_case", rollup)
            self.assertEqual(len(rollup.get("per_case") or []), len(payload.get("case_ids") or []))

    def test_export_rollout_readiness_baseline_can_print_json_to_stdout(self):
        script = BASE_DIR / "scripts" / "export_rollout_readiness_baseline.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--stdout"],
            cwd=str(BASE_DIR.parent),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload.get("ok"))
        self.assertIn("import_chain_rollup", payload)
        self.assertEqual(
            (payload.get("import_chain_rollup") or {}).get("case_count"),
            len(payload.get("case_ids") or []),
        )
        self.assertIn("status", payload.get("import_chain_rollup") or {})
        first_row = ((payload.get("readiness_release_board") or {}).get("cases") or [{}])[0]
        self.assertIn("final_report_present", first_row)
        self.assertIn("final_report_status", first_row)
        self.assertIn("final_report_release_board_status", first_row)

    def test_batch_compliance_auditor_case_ids_follow_loop_config(self):
        scripts = str(BASE_DIR / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from batch_hydrodesk_compliance_auditor import resolve_audit_case_ids

        ids = resolve_audit_case_ids()
        self.assertEqual(
            ids,
            [
                "zhongxian",
                "xuhonghe",
                "yinchuojiliao",
                "jiaodongtiaoshui",
                "daduhe",
                "yjdt",
            ],
        )
