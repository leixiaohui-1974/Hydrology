from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from export_case_modeling_hints import derive_modeling_hints


def test_derive_modeling_hints_prioritizes_workflows_from_graphify_signals(monkeypatch) -> None:
    monkeypatch.setattr("export_case_modeling_hints.load_case_config", lambda case_id: {"case_id": case_id, "project_type": "canal"})
    monkeypatch.setattr(
        "export_case_modeling_hints.run_readiness",
        lambda case_id, config_path, rules_path: {
            "summary": {
                "entry_case_manifest_source": "default_manifest",
                "entry_source_bundle_source": "data_pack_pointer",
                "entry_outlets_source": "contracts_default",
                "entry_simulation_config_source": "case_config",
                "entry_source_import_session_source": "manifest_latest",
                "source_import_session_present": True,
                "source_import_session_path": "cases/demo/contracts/source_import_session.latest.json",
                "source_import_mode": "copied_contract",
                "source_import_record_count": 7,
                "source_imported_at": "2026-04-09T00:00:00+00:00",
                "graphify_supports_auto_modeling_hints": True,
                "graphify_modeling_signal_counts": {
                    "terrain": 1,
                    "topology": 2,
                    "geometry": 0,
                    "boundary": 1,
                    "control": 1,
                },
                "pipeline_contract_ready": False,
                "workflow_data_ok": 20,
                "workflow_data_gap": 3,
            },
            "graphify_sidecar": {
                "artifacts": [{"kind": "graph_report", "path": "cases/demo/graphify/GRAPH_REPORT.md"}],
            },
        },
    )

    payload = derive_modeling_hints("demo_case", ROOT / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml", ROOT / "configs" / "workflow_feasibility_rules.yaml")
    hints = payload["hints"]
    assert hints["graphify_supports_auto_modeling_hints"] is True
    assert hints["entry_sources"]["source_bundle"] == "data_pack_pointer"
    assert hints["entry_sources"]["import_session"] == "manifest_latest"
    assert hints["source_import_session"]["present"] is True
    assert hints["source_import_session"]["path"] == "cases/demo/contracts/source_import_session.latest.json"
    assert hints["suggested_workflows"][:3] == ["source_to_delineation", "section_analysis", "model"]
    assert "cascade" in hints["suggested_workflows"]
    assert hints["workflow_recommendations"]["stage_activation_guidance"]["hydrology"]["status"] == "deferred"
    assert hints["workflow_recommendations"]["stage_activation_guidance"]["hydraulics"]["status"] == "recommended"
    assert hints["workflow_recommendations"]["stage_activation_guidance"]["assimilation"]["status"] == "recommended"
    assert hints["workflow_recommendations"]["deferred_stages"] == ["hydrology"]


def test_derive_modeling_hints_keeps_hydrology_default_for_cascade_hydro_cases(monkeypatch) -> None:
    monkeypatch.setattr("export_case_modeling_hints.load_case_config", lambda case_id: {"case_id": case_id, "project_type": "cascade_hydro"})
    monkeypatch.setattr(
        "export_case_modeling_hints.run_readiness",
        lambda case_id, config_path, rules_path: {
            "summary": {
                "entry_case_manifest_source": "default_manifest",
                "entry_source_bundle_source": "manifest_latest",
                "entry_outlets_source": "manifest_latest",
                "entry_simulation_config_source": "case_config",
                "entry_source_import_session_source": "manifest_latest",
                "source_import_session_present": True,
                "source_import_session_path": "cases/demo/contracts/source_import_session.latest.json",
                "source_import_mode": "copied_contract",
                "source_import_record_count": 5,
                "source_imported_at": "2026-04-13T00:00:00+00:00",
                "graphify_supports_auto_modeling_hints": False,
                "graphify_modeling_signal_counts": {},
                "pipeline_contract_ready": True,
                "workflow_data_ok": 20,
                "workflow_data_gap": 3,
            },
            "graphify_sidecar": {"artifacts": []},
        },
    )

    payload = derive_modeling_hints("demo_case", ROOT / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml", ROOT / "configs" / "workflow_feasibility_rules.yaml")
    hints = payload["hints"]
    hydrology = hints["workflow_recommendations"]["stage_activation_guidance"]["hydrology"]

    assert hints["project_type"] == "cascade_hydro"
    assert hydrology["status"] == "default"
    assert "reason" not in hydrology
    assert "hydrology" not in hints["workflow_recommendations"]["deferred_stages"]
