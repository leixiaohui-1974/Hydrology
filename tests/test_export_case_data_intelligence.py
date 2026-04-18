import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import export_case_data_intelligence
from export_case_data_intelligence import build_case_data_profile
from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids


def test_build_case_data_profile_emits_six_asset_categories(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": ["cases/demo/raw"],
            "case_manifest_path": "cases/demo/contracts/case_manifest.json",
            "topology_json_paths": ["cases/demo/contracts/topology.json"],
            "sqlite_paths": ["cases/demo/obs/demo.sqlite3"],
            "data_sources": {
                "terrain": {
                    "dem": {"path": "cases/demo/raw/dem.tif"},
                    "river_network": {"path": "cases/demo/raw/river.shp"},
                },
                "hydrology": {
                    "rainfall": {"path": "cases/demo/raw/rainfall.csv"},
                    "catchment": {"delineation_path": "cases/demo/raw/catchment.nc"},
                },
                "scada": {
                    "database": {"path": "cases/demo/obs/demo.sqlite3"},
                },
                "structures": {
                    "cross_sections": {"path": "cases/demo/raw/sections.csv"},
                    "gate_curves": {"path": "cases/demo/raw/gate_curves.csv", "count": 3},
                },
            },
            "model": {
                "boundary": {
                    "upstream": {"series_path": "cases/demo/raw/upstream.csv"},
                    "downstream": {"series_path": "cases/demo/raw/downstream.csv"},
                },
                "reservoirs": [{"id": "r1", "name": "Demo Reservoir"}],
                "actuators": [{"id": "g1", "type": "gate"}],
            },
            "results": {
                "pipeline_summary": "research/e2e_reports/demo/pipeline_summary.json",
            },
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (
            Path("/repo/cases/demo/manifest.yaml"),
            {"title": "Demo case"},
        ),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: (
            {"stations": [{"id": "s1", "control_area_km2": 12.5}]},
            {
                "data_sources": {
                    "structures": {
                        "topology": {"path": "control/demo_topology.json"},
                        "turbine_curves": {"path": "control/turbine_curves.csv"},
                    }
                }
            },
        ),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [
                {
                    "role": "design_report",
                    "artifact": {
                        "path": "cases/demo/docs/design_report.pdf",
                        "artifact_type": "pdf",
                    },
                },
                {
                    "role": "historical_operations",
                    "artifact": {
                        "path": "cases/demo/docs/ops.xlsx",
                        "artifact_type": "xlsx",
                    },
                },
            ]
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {
            "record_count": 5,
            "imported_at": "2026-04-12T00:00:00+00:00",
        },
    )

    payload = build_case_data_profile("demo")

    categories = payload["asset_profile"]["categories"]
    assert set(categories) == {
        "terrain_and_spatial",
        "hydrology",
        "hydraulics",
        "engineering_operation",
        "runtime_validation",
        "document_knowledge",
    }
    assert categories["terrain_and_spatial"]["asset_count"] >= 3
    assert categories["hydrology"]["asset_count"] >= 2
    assert categories["hydraulics"]["asset_count"] >= 3
    assert categories["engineering_operation"]["asset_count"] >= 3
    assert categories["runtime_validation"]["asset_count"] >= 4
    assert categories["document_knowledge"]["asset_count"] >= 3
    assert payload["coverage_summary"]["available_categories"] == 6


def test_build_case_data_profile_uses_data_signals_not_case_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": [],
            "sqlite_paths": [],
            "data_sources": {
                "terrain": {"dem": {"path": None}},
                "hydrology": {"rainfall": {"path": None}},
                "structures": {"gate_curves": {"path": None, "count": 0}},
            },
            "model": {"boundary": {}, "reservoirs": [], "actuators": []},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {"records": []},
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("daduhe")

    assert payload["coverage_summary"]["available_categories"] == 2
    assert payload["asset_profile"]["categories"]["terrain_and_spatial"]["asset_count"] == 0
    assert payload["asset_profile"]["categories"]["hydrology"]["asset_count"] == 0


def test_main_batches_profiles_from_loop_config(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_load_loop_yaml(workspace, config_path):
        seen["load_loop_yaml"] = (workspace, config_path)
        return {"case_ids": ["alpha", "beta"]}

    def fake_resolve_case_ids(cfg, workspace):
        seen["resolve_case_ids"] = (cfg, workspace)
        return ["alpha", "beta"]

    monkeypatch.setattr(
        export_case_data_intelligence,
        "load_loop_yaml",
        fake_load_loop_yaml,
    )
    monkeypatch.setattr(
        export_case_data_intelligence,
        "resolve_case_ids",
        fake_resolve_case_ids,
    )
    monkeypatch.setattr(
        export_case_data_intelligence,
        "run_export",
        lambda case_id: {"case_id": case_id, "asset_profile": {"categories": {}}, "coverage_summary": {"available_categories": 0, "total_categories": 6}},
    )
    monkeypatch.setattr(sys, "argv", ["export_case_data_intelligence.py"])

    assert export_case_data_intelligence.main() == 0

    stdout = json.loads(capsys.readouterr().out)
    assert stdout["case_ids"] == ["alpha", "beta"]
    assert [profile["case_id"] for profile in stdout["profiles"]] == ["alpha", "beta"]

    cfg_workspace, cfg_path = seen["load_loop_yaml"]
    assert cfg_workspace == export_case_data_intelligence._WORKSPACE
    assert cfg_path == export_case_data_intelligence.DEFAULT_CONFIG

    resolved_cfg, resolve_workspace = seen["resolve_case_ids"]
    assert resolved_cfg == {"case_ids": ["alpha", "beta"]}
    assert resolve_workspace == export_case_data_intelligence._WORKSPACE


def test_persist_latest_writes_case_profiles(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(export_case_data_intelligence, "_WORKSPACE", tmp_path)
    payload = {
        "case_ids": ["alpha", "beta"],
        "profiles": [
            {"case_id": "alpha", "workflow_planning": {}},
            {"case_id": "beta", "workflow_planning": {}},
        ],
    }

    persisted = export_case_data_intelligence._persist_latest(payload)

    assert persisted["latest_output_paths"] == [
        "cases/alpha/contracts/case_data_intelligence.latest.json",
        "cases/beta/contracts/case_data_intelligence.latest.json",
    ]
    assert (tmp_path / "cases/alpha/contracts/case_data_intelligence.latest.json").is_file()
    assert (tmp_path / "cases/beta/contracts/case_data_intelligence.latest.json").is_file()


def test_batch_builds_real_profiles_for_rollout_cases() -> None:
    loop_cfg = load_loop_yaml(
        export_case_data_intelligence._WORKSPACE,
        export_case_data_intelligence.DEFAULT_CONFIG,
    )
    case_ids = resolve_case_ids(loop_cfg, export_case_data_intelligence._WORKSPACE)

    payload = export_case_data_intelligence._batch(case_ids)

    assert case_ids == [
        "zhongxian",
        "xuhonghe",
        "yinchuojiliao",
        "jiaodongtiaoshui",
        "daduhe",
        "yjdt",
    ]
    assert payload["case_ids"] == case_ids
    assert len(payload["profiles"]) == 6
    assert all(len(profile["asset_profile"]["categories"]) == 6 for profile in payload["profiles"])

    profile_by_case = {profile["case_id"]: profile for profile in payload["profiles"]}
    assert profile_by_case["daduhe"]["asset_profile"]["categories"]["terrain_and_spatial"]["available"] is True
    assert profile_by_case["daduhe"]["asset_profile"]["categories"]["hydrology"]["available"] is True
    assert profile_by_case["zhongxian"]["asset_profile"]["categories"]["hydraulics"]["available"] is True
    assert profile_by_case["zhongxian"]["asset_profile"]["categories"]["engineering_operation"]["available"] is True
    daduhe_docs = profile_by_case["daduhe"]["asset_profile"]["categories"]["document_knowledge"]
    daduhe_runtime = profile_by_case["daduhe"]["asset_profile"]["categories"]["runtime_validation"]
    daduhe_operation = profile_by_case["daduhe"]["asset_profile"]["categories"]["engineering_operation"]
    assert daduhe_docs["asset_count"] >= 3
    assert daduhe_runtime["asset_count"] >= 3
    assert daduhe_operation["asset_count"] >= 3
    assert "watershed_delineation" in profile_by_case["daduhe"]["workflow_planning"]["recommended_path"]
    assert "hydrological_simulation" in profile_by_case["daduhe"]["workflow_planning"]["recommended_path"]
    if profile_by_case["zhongxian"]["case_characteristics"]["project_type"] != "canal":
        assert "watershed_delineation" in profile_by_case["zhongxian"]["workflow_planning"]["blocked_path"]
    else:
        assert "watershed_delineation" not in profile_by_case["zhongxian"]["workflow_planning"]["blocked_path"]
        assert "watershed_delineation" not in profile_by_case["zhongxian"]["workflow_planning"]["recommended_path"]


def test_build_case_data_profile_adds_authenticity_fields_from_source_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": [],
            "sqlite_paths": [],
            "data_sources": {
                "terrain": {
                    "dem": {"path": "cases/demo/raw/dem.tif"},
                },
                "hydrology": {
                    "catchment": {"delineation_path": "cases/demo/raw/catchment.nc"},
                },
            },
            "model": {"boundary": {}, "reservoirs": [], "actuators": []},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [
                {
                    "role": "dem_primary",
                    "needs_review": False,
                    "artifact": {
                        "path": "cases/demo/raw/dem.tif",
                        "artifact_type": "tif",
                    },
                    "evidence": ["source_a.json"],
                },
                {
                    "role": "catchment_seed_or_existing_delineation",
                    "needs_review": True,
                    "artifact": {
                        "path": "cases/demo/raw/catchment.nc",
                        "artifact_type": "nc",
                        "metadata": {
                            "semantic_status": "do_not_use_as_primary_checkpoint_source",
                        },
                    },
                    "evidence": ["source_b.json"],
                },
            ]
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")
    terrain_asset = payload["asset_profile"]["categories"]["terrain_and_spatial"]["assets"][0]
    hydrology_asset = payload["asset_profile"]["categories"]["hydrology"]["assets"][0]

    assert terrain_asset["authenticity"]["source_type"] == "referenced_source"
    assert terrain_asset["authenticity"]["traceability"] == "evidence_backed"
    assert terrain_asset["authenticity"]["model_readiness"] == "direct"

    assert hydrology_asset["authenticity"]["source_type"] == "review_required"
    assert hydrology_asset["authenticity"]["traceability"] == "evidence_backed"
    assert hydrology_asset["authenticity"]["model_readiness"] == "review_required"
    assert payload["authenticity_summary"]["review_required_assets"] == 1
    assert payload["authenticity_risks"][0]["asset_key"] == "catchment"


def test_build_case_data_profile_marks_config_only_assets_as_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": [],
            "sqlite_paths": [],
            "data_sources": {
                "scada": {"database": {"path": "cases/demo/obs/demo.sqlite3"}},
            },
            "model": {"boundary": {}, "reservoirs": [], "actuators": []},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {"records": []},
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")
    runtime_asset = payload["asset_profile"]["categories"]["runtime_validation"]["assets"][0]

    assert runtime_asset["authenticity"]["source_type"] == "configured_path"
    assert runtime_asset["authenticity"]["traceability"] == "config_only"
    assert runtime_asset["authenticity"]["model_readiness"] == "candidate"


def test_build_case_data_profile_surfaces_source_bundle_gaps_as_risks(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": [],
            "sqlite_paths": [],
            "data_sources": {},
            "model": {"boundary": {}, "reservoirs": [], "actuators": []},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [],
            "gaps": ["dem", "landuse"],
            "review_required": ["resource_gap_review"],
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")

    assert payload["authenticity_summary"]["missing_bundle_gaps"] == 2
    assert any(risk["risk_type"] == "missing_source_bundle_gap" for risk in payload["authenticity_risks"])


def test_build_case_data_profile_recommends_hydrology_path_when_core_truth_is_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": ["cases/demo/contracts/topology.json"],
            "sqlite_paths": [],
            "data_sources": {
                "terrain": {
                    "dem": {"path": "cases/demo/raw/dem.tif"},
                },
                "hydrology": {
                    "rainfall": {"path": "cases/demo/raw/rainfall.csv"},
                    "catchment": {"delineation_path": "cases/demo/raw/catchment.nc"},
                },
                "structures": {
                    "cross_sections": {"path": "cases/demo/raw/sections.csv"},
                },
            },
            "model": {
                "boundary": {
                    "upstream": {"series_path": "cases/demo/raw/upstream.csv"},
                    "downstream": {"series_path": "cases/demo/raw/downstream.csv"},
                },
                "reservoirs": [],
                "actuators": [{"id": "g1", "type": "gate"}],
            },
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [
                {"artifact": {"path": "cases/demo/raw/dem.tif"}, "evidence": ["a.json"], "needs_review": False},
                {"artifact": {"path": "cases/demo/raw/rainfall.csv"}, "evidence": ["b.json"], "needs_review": False},
                {"artifact": {"path": "cases/demo/raw/catchment.nc"}, "evidence": ["c.json"], "needs_review": False},
            ]
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")

    assert "watershed_delineation" in payload["workflow_planning"]["recommended_path"]
    assert "hydrological_simulation" in payload["workflow_planning"]["recommended_path"]
    assert "hydraulic_control_modeling" in payload["workflow_planning"]["recommended_path"]
    assert payload["workflow_planning"]["blocked_path"] == []


def test_build_case_data_profile_blocks_hydrology_path_when_truth_is_missing_or_risky(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": ["cases/demo/contracts/topology.json"],
            "sqlite_paths": ["cases/demo/obs/demo.sqlite3"],
            "data_sources": {
                "hydrology": {
                    "catchment": {"delineation_path": "cases/demo/raw/catchment.nc"},
                },
                "structures": {
                    "topology": {"path": "cases/demo/contracts/topology.json"},
                },
                "scada": {"database": {"path": "cases/demo/obs/demo.sqlite3"}},
            },
            "model": {"boundary": {}, "reservoirs": [], "actuators": [{"id": "g1", "type": "gate"}]},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [
                {
                    "artifact": {
                        "path": "cases/demo/raw/catchment.nc",
                        "metadata": {"semantic_status": "do_not_use_as_primary_checkpoint_source"},
                    },
                    "evidence": ["c.json"],
                    "needs_review": True,
                }
            ],
            "gaps": ["dem", "rainfall"],
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")

    assert "watershed_delineation" in payload["workflow_planning"]["blocked_path"]
    assert "hydrological_simulation" in payload["workflow_planning"]["blocked_path"]
    assert "hydraulic_control_modeling" in payload["workflow_planning"]["recommended_path"]
    assert set(payload["workflow_planning"]["missing_evidence"]) == {"dem", "rainfall", "catchment"}


def test_build_case_data_profile_emits_model_change_advice_for_truth_and_strategy_gaps(monkeypatch) -> None:
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_config",
        lambda case_id: {
            "scan_dirs": [],
            "case_manifest_path": f"cases/{case_id}/contracts/case_manifest.json",
            "topology_json_paths": ["cases/demo/contracts/topology.json"],
            "sqlite_paths": ["cases/demo/obs/demo.sqlite3"],
            "data_sources": {
                "hydrology": {
                    "catchment": {"delineation_path": "cases/demo/raw/catchment.nc"},
                },
                "structures": {
                    "topology": {"path": "cases/demo/contracts/topology.json"},
                },
                "scada": {"database": {"path": "cases/demo/obs/demo.sqlite3"}},
            },
            "model": {"boundary": {}, "reservoirs": [], "actuators": [{"id": "g1", "type": "gate"}]},
            "results": {},
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence.load_case_manifest",
        lambda case_id, manifest_path=None: (Path(f"/repo/cases/{case_id}/manifest.yaml"), {}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_control_payload",
        lambda case_id: ({}, {"data_sources": {}}),
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_bundle",
        lambda case_id: {
            "records": [
                {
                    "artifact": {
                        "path": "cases/demo/raw/catchment.nc",
                        "metadata": {"semantic_status": "do_not_use_as_primary_checkpoint_source"},
                    },
                    "evidence": ["c.json"],
                    "needs_review": True,
                }
            ],
            "gaps": ["dem", "rainfall"],
        },
    )
    monkeypatch.setattr(
        "export_case_data_intelligence._load_source_import_session",
        lambda case_id: {},
    )

    payload = build_case_data_profile("demo")
    advice = payload["workflow_planning"]["model_change_advice"]
    layers = payload["learning_strategy"]

    assert any(item["advice_type"] == "data_authenticity" for item in advice)
    assert any(item["advice_type"] == "workflow_strategy" for item in advice)
    assert any("catchment" in " ".join(item.get("evidence_keys", [])) for item in advice)
    assert set(layers) == {"parameter_learning", "model_strategy_learning", "model_change_advice"}
    assert layers["parameter_learning"]["status"] == "deferred"
    assert layers["model_strategy_learning"]["status"] == "recommended"
    assert layers["model_change_advice"]["status"] == "required"
