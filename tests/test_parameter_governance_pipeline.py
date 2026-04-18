import json
import sys
from pathlib import Path

import workflows.run_case_pipeline as run_case_pipeline

ROOT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT_DIR.parent
SIX_CASE_IDS = [
    "daduhe",
    "zhongxian",
    "xuhonghe",
    "yinchuojiliao",
    "jiaodongtiaoshui",
    "yjdt",
]



def test_run_case_pipeline_calls_parameter_governance_before_watershed(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    imports: list[str] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: imports.append(case_id) or {"ok": True, "case_id": case_id},
    )
    manifest_path = tmp_path / "cases" / "daduhe" / "manifest.yaml"
    contracts_dir = manifest_path.parent / "contracts"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: daduhe\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "daduhe",
            "--case-manifest",
            str(manifest_path),
            "--source-bundle-json",
            "tmp/source_bundle.json",
            "--outlets-json",
            "tmp/outlets.json",
            "--phase",
            "watershed",
        ],
    )

    run_case_pipeline.main()

    assert imports == ["daduhe"]
    assert [name for name, _ in calls[:3]] == [
        "build_data_pack.py",
        "build_parameter_governance.py",
        "run_watershed_delineation.py",
    ]
    data_pack_args = calls[0][1]
    assert "--output" in data_pack_args
    assert data_pack_args[data_pack_args.index("--output") + 1] == str(contracts_dir / "data_pack.latest.json")
    watershed_args = calls[2][1]
    assert "--parameter-governance-json" in watershed_args
    assert watershed_args[watershed_args.index("--metadata-out") + 1] == str(contracts_dir / "workflow_run.json")



def test_run_watershed_delineation_requires_governance_json(monkeypatch, tmp_path: Path) -> None:
    import workflows.run_watershed_delineation as target

    data_pack = tmp_path / "data_pack.json"
    data_pack.write_text(
        '{"source_bundle_json":"tmp/source_bundle.json","outlets_json":"tmp/outlets.json","review_gates":{"basin_validation_json":"tmp/basin_validation.json"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_watershed_delineation.py",
            "--case-id",
            "daduhe",
            "--data-pack-json",
            str(data_pack),
        ],
    )

    try:
        target.main()
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("Expected governance gate to reject missing governance JSON")



def test_run_case_pipeline_passes_governance_into_hydrological_simulation(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "daduhe" / "manifest.yaml"
    contracts_dir = manifest_path.parent / "contracts"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: daduhe\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": "tmp/simulation.yaml",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "daduhe",
            "--case-manifest",
            str(manifest_path),
            "--source-bundle-json",
            "tmp/source_bundle.json",
            "--outlets-json",
            "tmp/outlets.json",
            "--simulation-config",
            "tmp/simulation.yaml",
            "--phase",
            "simulation",
        ],
    )

    run_case_pipeline.main()

    simulation_call = next(args for name, args in calls if name == "run_hydrological_simulation.py")
    assert "--parameter-governance-json" in simulation_call
    assert simulation_call[simulation_call.index("--data-pack-json") + 1] == str(contracts_dir / "data_pack.latest.json")
    assert simulation_call[simulation_call.index("--parameter-governance-json") + 1] == str(contracts_dir / "parameter_governance.latest.json")


def test_run_case_pipeline_release_phase_writes_review_and_release_to_contracts(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "daduhe" / "manifest.yaml"
    contracts_dir = manifest_path.parent / "contracts"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: daduhe\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "daduhe",
            "--case-manifest",
            str(manifest_path),
            "--source-bundle-json",
            "tmp/source_bundle.json",
            "--outlets-json",
            "tmp/outlets.json",
            "--phase",
            "release",
        ],
    )

    run_case_pipeline.main()

    review_call = next(args for name, args in calls if name == "build_review_bundle.py")
    assert review_call[review_call.index("--review-output") + 1] == str(contracts_dir / "review_bundle.json")
    release_call = next(args for name, args in calls if name == "build_release_manifest.py")
    assert release_call[release_call.index("--workflow-run") + 1] == str(contracts_dir / "workflow_run.json")
    assert release_call[release_call.index("--review-bundle") + 1] == str(contracts_dir / "review_bundle.json")
    assert release_call[release_call.index("--output") + 1] == str(contracts_dir / "release_manifest.json")
    modeling_hints_path = contracts_dir / "modeling_hints.latest.json"
    assert str(modeling_hints_path) in release_call
    final_report_call = next(args for name, args in calls if name == "build_final_report.py")
    assert final_report_call[final_report_call.index("--review-bundle") + 1] == str(contracts_dir / "review_bundle.json")
    assert final_report_call[final_report_call.index("--release-manifest") + 1] == str(contracts_dir / "release_manifest.json")
    assert final_report_call[final_report_call.index("--output") + 1] == str(contracts_dir / "final_report.latest.json")


def test_run_case_pipeline_writes_modeling_hints_contract(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    contracts_dir = manifest_path.parent / "contracts"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_safe_modeling_hints",
        lambda case_id: {
            "case_id": case_id,
            "suggested_workflows": ["source_to_delineation", "model"],
            "graphify_supports_auto_modeling_hints": True,
            "graphify_modeling_signal_counts": {"topology": 2},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "watershed",
        ],
    )

    run_case_pipeline.main()

    modeling_hints_path = contracts_dir / "modeling_hints.latest.json"
    payload = json.loads(modeling_hints_path.read_text(encoding="utf-8"))
    assert payload["case_id"] == "demo_case"
    assert payload["suggested_workflows"] == ["source_to_delineation", "model"]
    assert payload["graphify_supports_auto_modeling_hints"] is True


def test_run_case_pipeline_resolves_manifest_source_bundle_and_outlets_from_case_id(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "daduhe",
            "--phase",
            "watershed",
        ],
    )

    run_case_pipeline.main()

    data_pack_call = next(args for name, args in calls if name == "build_data_pack.py")
    assert data_pack_call[data_pack_call.index("--case-manifest") + 1].endswith("cases/daduhe/manifest.yaml")
    assert data_pack_call[data_pack_call.index("--source-bundle-json") + 1].endswith("cases/daduhe/contracts/source_bundle.contract.json")
    assert data_pack_call[data_pack_call.index("--outlets-json") + 1].endswith("cases/daduhe/contracts/outlets.normalized.json")


def test_run_case_pipeline_defaults_simulation_config_from_case_yaml(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "daduhe",
            "--phase",
            "simulation",
        ],
    )

    run_case_pipeline.main()

    simulation_call = next(args for name, args in calls if name == "run_hydrological_simulation.py")
    assert simulation_call[simulation_call.index("--simulation-config") + 1].endswith("Hydrology/configs/daduhe.yaml")


def test_run_case_pipeline_falls_back_to_case_config_and_standard_contract_paths(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "generic_case" / "manifest.yaml"
    contracts_dir = manifest_path.parent / "contracts"
    product_outputs = manifest_path.parent / "source_selection" / "product_outputs"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    product_outputs.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: generic_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": str(contracts_dir / "source_bundle.contract.json"),
            "outlets_json": str(product_outputs / "outlets.delineation_ready.json"),
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "generic_case",
            "--case-manifest",
            str(manifest_path),
            "--phase",
            "watershed",
        ],
    )

    run_case_pipeline.main()

    data_pack_call = next(args for name, args in calls if name == "build_data_pack.py")
    assert data_pack_call[data_pack_call.index("--source-bundle-json") + 1] == str(contracts_dir / "source_bundle.contract.json")
    assert data_pack_call[data_pack_call.index("--outlets-json") + 1] == str(product_outputs / "outlets.delineation_ready.json")


def test_six_case_parameter_governance_contracts_cover_all_eight_stages() -> None:
    expected_stages = [
        "watershed_delineation",
        "hydrology",
        "hydraulics",
        "coupling",
        "assimilation",
        "identification",
        "scheduling_control",
        "sil_odd",
    ]
    for case_id in SIX_CASE_IDS:
        contract_path = WORKSPACE_ROOT / "cases" / case_id / "contracts" / "parameter_governance.latest.json"
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "parameter_governance_multistage.v1"
        assert payload["canonical_stage_order"] == expected_stages
        assert list((payload.get("stages") or {}).keys()) == expected_stages
        for stage in expected_stages:
            parameters = payload["stages"][stage]
            assert parameters, f"{case_id}:{stage}"
            for item in parameters:
                assert "default_value" in item, f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert "bounds" in item, f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert item.get("source_of_truth"), f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert "sensitivity_enabled" in item, f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert "calibration_enabled" in item, f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert "assimilation_enabled" in item, f"{case_id}:{stage}:{item.get('parameter_id')}"
                assert item.get("validation_metric_links") is not None, f"{case_id}:{stage}:{item.get('parameter_id')}"


def test_run_hydraulic_simulation_reads_multistage_parameter_governance(monkeypatch) -> None:
    import workflows.run_hydraulic_simulation as target

    captured: dict[str, object] = {}

    def fake_run_simulation(case_id: str, mode: str, hydraulics_activation: dict) -> dict:
        captured["case_id"] = case_id
        captured["mode"] = mode
        captured["hydraulics_activation"] = hydraulics_activation
        return {"replay": {"avg_nse": 0.91}, "cascade": {"avg_nse": 0.87}}

    monkeypatch.setattr(target, "run_simulation", fake_run_simulation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_hydraulic_simulation.py",
            "--case-id",
            "daduhe",
            "--parameter-governance-json",
            str(WORKSPACE_ROOT / "cases" / "daduhe" / "contracts" / "parameter_governance.latest.json"),
        ],
    )

    target.main()

    assert captured["case_id"] == "daduhe"
    assert captured["mode"] == "all"
    assert captured["hydraulics_activation"]["section_substitute_mode"] == "observed"
    assert captured["hydraulics_activation"]["manning_n_scale"] == 1.0


def test_run_case_pipeline_dry_run_emits_modeling_hints_and_planned_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id, "imported_at": "2026-04-09T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_safe_modeling_hints",
        lambda case_id: {
            "case_id": case_id,
            "suggested_workflows": ["source_to_delineation", "model"],
            "graphify_supports_auto_modeling_hints": True,
            "graphify_modeling_signal_counts": {"topology": 2},
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_source_import_session_summary",
        lambda case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{case_id}/contracts/source_import_session.latest.json",
            "source_mode": "copied_contract",
            "record_count": 3,
            "imported_at": "2026-04-09T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "simulation",
            "--dry-run",
        ],
    )

    run_case_pipeline.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sourcebundle_import"]["ok"] is True
    assert payload["source_import_session"]["present"] is True
    assert payload["source_import_session"]["path"] == "cases/demo_case/contracts/source_import_session.latest.json"
    assert payload["modeling_hints"]["graphify_supports_auto_modeling_hints"] is True
    assert payload["modeling_hints"]["suggested_workflows"] == ["source_to_delineation", "model"]
    assert [row["step"] for row in payload["planned_commands"]] == [
        "build_data_pack",
        "build_parameter_governance",
        "run_watershed_delineation",
        "run_hydrological_simulation",
    ]
    assert calls == []


def test_run_case_pipeline_full_dry_run_exposes_source_to_delivery_contract_chain(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id, "imported_at": "2026-04-12T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": str(tmp_path / "contracts" / "source_bundle.contract.json"),
            "outlets_json": str(tmp_path / "contracts" / "outlets.normalized.json"),
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_source_import_session_summary",
        lambda case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{case_id}/contracts/source_import_session.latest.json",
            "source_mode": "copied_contract",
            "record_count": 5,
            "imported_at": "2026-04-12T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "full",
            "--dry-run",
        ],
    )

    run_case_pipeline.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["entrypoint_scope"] == "source_to_delivery"
    assert [row["stage"] for row in payload["stage_chain"]] == [
        "source",
        "data_pack",
        "watershed",
        "hydrology",
        "review",
        "release",
        "final_report",
    ]
    assert payload["stage_chain"][0]["key_contracts"][0]["name"] == "case_manifest"
    assert payload["stage_chain"][0]["key_contracts"][-1]["name"] == "source_import_session"
    assert [row["name"] for row in payload["delivery_targets"]] == [
        "review_bundle",
        "release_manifest",
        "final_report",
        "universal_report",
    ]
    critical_contract_names = [row["name"] for row in payload["critical_contracts"]]
    assert "source_bundle" in critical_contract_names
    assert "data_pack" in critical_contract_names
    assert "parameter_governance" in critical_contract_names
    assert "workflow_run" in critical_contract_names
    assert "release_manifest" in critical_contract_names
    assert "final_report" in critical_contract_names
    assert [row["step"] for row in payload["planned_commands"]] == [
        "build_data_pack",
        "build_parameter_governance",
        "run_watershed_delineation",
        "run_hydrological_simulation",
        "build_review_bundle",
        "build_release_manifest",
        "build_final_report",
        "generate_universal_report",
    ]
    assert calls == []


def test_run_case_pipeline_dry_run_surfaces_empty_outlets_as_actionable_source_gap(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    outlets_path = contracts_dir / "outlets.normalized.json"
    outlets_path.write_text(json.dumps({"count": 0, "outlets": []}, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")

    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id, "imported_at": "2026-04-13T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": str(contracts_dir / "source_bundle.contract.json"),
            "outlets_json": str(outlets_path),
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_source_import_session_summary",
        lambda case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{case_id}/contracts/source_import_session.latest.json",
            "source_mode": "copied_contract",
            "record_count": 5,
            "imported_at": "2026-04-13T00:00:00+00:00",
            "scan_dirs": [f"cases/{case_id}/ingest/raw"],
            "web_seed_files": [f"cases/{case_id}/ingest/web/seed_queries.json"],
            "sqlite_import_reason": "source_bundle_has_no_complete_real_observation_roles",
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_web_source_session_summary",
        lambda case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{case_id}/contracts/web_source_session.latest.json",
            "status": "seeded",
            "seed_query_count": 1,
            "seed_url_count": 0,
            "discovered_source_count": 0,
            "download_file_count": 0,
            "needs_web_fetch": True,
            "public_data_inventory_contract": f"cases/{case_id}/contracts/public_data_inventory.latest.json",
            "public_data_summary": {
                "record_count": 1,
                "downloaded_count": 0,
                "blocked_count": 1,
                "available_public_data_kinds": [],
                "blocked_public_data_kinds": ["hydrography"],
                "status_counts": {"http_error": 1},
            },
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_safe_modeling_hints",
        lambda case_id: {
            "case_id": case_id,
            "project_type": "cascade_hydro",
            "workflow_recommendations": {"deferred_stages": [], "stage_activation_guidance": {}},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "full",
            "--dry-run",
        ],
    )

    run_case_pipeline.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "outlets_empty" in payload["missing_inputs"]
    assert payload["web_source_session"]["present"] is True
    assert payload["web_source_session"]["needs_web_fetch"] is True
    assert payload["web_source_session"]["public_data_inventory_contract"] == "cases/demo_case/contracts/public_data_inventory.latest.json"
    assert payload["web_source_session"]["public_data_summary"]["blocked_public_data_kinds"] == ["hydrography"]
    assert payload["source_gap_hints"][0]["kind"] == "outlets_empty"
    assert payload["source_gap_hints"][0]["project_type"] == "cascade_hydro"
    assert payload["source_gap_hints"][0]["recommended_public_data"] == ["dem", "landuse", "soil", "hydrography"]
    assert payload["source_gap_hints"][0]["public_data_inventory_contract"] == "cases/demo_case/contracts/public_data_inventory.latest.json"
    assert payload["source_gap_hints"][0]["public_data_summary"]["blocked_count"] == 1
    assert payload["source_gap_hints"][0]["case_local_scan_dirs"] == ["cases/demo_case/ingest/raw"]
    assert payload["source_gap_hints"][0]["web_seed_files"] == ["cases/demo_case/ingest/web/seed_queries.json"]


def test_run_case_pipeline_can_skip_auto_import_sourcebundle(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    imports: list[str] = []
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: imports.append(case_id) or {"ok": True, "case_id": case_id},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "data-pack",
            "--no-auto-import-sourcebundle",
        ],
    )

    run_case_pipeline.main()

    assert imports == []
    assert calls[0][0] == "build_data_pack.py"


def test_run_case_pipeline_respect_stage_guidance_blocks_deferred_hydrology(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda case_id: {"ok": True, "case_id": case_id},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "run_python",
        lambda path, args: calls.append((Path(path).name, list(args))),
    )
    manifest_path = tmp_path / "cases" / "demo_case" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": "tmp/source_bundle.json",
            "outlets_json": "tmp/outlets.json",
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_safe_modeling_hints",
        lambda case_id: {
            "case_id": case_id,
            "workflow_recommendations": {
                "deferred_stages": ["hydrology"],
                "stage_activation_guidance": {
                    "hydrology": {"status": "deferred", "matched_workflows": []},
                },
            },
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_case_pipeline.py",
            "--case-id",
            "demo_case",
            "--phase",
            "simulation",
            "--respect-stage-guidance",
        ],
    )

    try:
        run_case_pipeline.main()
    except ValueError as exc:
        assert "deferred by stage guidance" in str(exc)
    else:
        raise AssertionError("Expected deferred hydrology stage to block simulation")

    assert [name for name, _ in calls] == [
        "build_data_pack.py",
        "build_parameter_governance.py",
        "run_watershed_delineation.py",
    ]
