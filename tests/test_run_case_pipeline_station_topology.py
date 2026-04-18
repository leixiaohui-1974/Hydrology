from __future__ import annotations

import json
import sys
from pathlib import Path

import workflows.run_case_pipeline as run_case_pipeline


def test_run_case_pipeline_dry_run_preserves_outlets_empty_while_exposing_station_topology(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    case_id = "demo_case"
    manifest_path = tmp_path / "cases" / case_id / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    outlets_path = tmp_path / "contracts" / "outlets.normalized.json"
    outlets_path.parent.mkdir(parents=True, exist_ok=True)
    outlets_path.write_text(json.dumps({"count": 0, "outlets": []}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        run_case_pipeline,
        "import_case_sourcebundle",
        lambda requested_case_id: {"ok": True, "case_id": requested_case_id},
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": str(tmp_path / "contracts" / "source_bundle.contract.json"),
            "outlets_json": str(outlets_path),
            "simulation_config": str(tmp_path / "simulation.yaml"),
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_source_import_session_summary",
        lambda requested_case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{requested_case_id}/contracts/source_import_session.latest.json",
            "source_mode": "copied_contract",
            "record_count": 5,
            "imported_at": "2026-04-13T00:00:00+00:00",
            "scan_dirs": [f"cases/{requested_case_id}/ingest/raw"],
            "web_seed_files": [],
            "sqlite_import_reason": "skipped",
            "station_topology_contract": f"cases/{requested_case_id}/contracts/station_topology.latest.json",
            "station_topology_summary": {
                "station_count": 5,
                "geo_located_station_count": 0,
                "alias_count": 3,
                "boundary_hints_present": True,
            },
            "topology_status": "named_only",
            "station_geolocation_contract": f"cases/{requested_case_id}/contracts/station_geolocation.latest.json",
            "station_geolocation_summary": {
                "station_count": 5,
                "context_evidence_count": 1,
                "query_ready_station_count": 5,
                "geo_located_station_count": 0,
                "blocked_public_data_kinds": ["hydrography"],
            },
            "geolocation_status": "context_linked",
            "station_geocode_candidates_contract": f"cases/{requested_case_id}/contracts/station_geocode_candidates.latest.json",
            "station_proxy_outlet_anchors_contract": f"cases/{requested_case_id}/contracts/station_proxy_outlet_anchors.latest.json",
            "station_proxy_outlet_anchors_summary": {
                "anchor_count": 2,
                "owner_count": 2,
                "admin_area_anchor_count": 1,
                "locality_anchor_count": 1,
            },
            "proxy_anchor_status": "proxy_review_ready",
            "station_outlet_candidates_contract": f"cases/{requested_case_id}/contracts/station_outlet_candidates.latest.json",
            "station_outlet_candidates_summary": {
                "candidate_count": 1,
                "unassigned_case_proxy_anchor_count": 1,
                "eligible_for_delineation_count": 0,
            },
            "outlet_candidate_status": "proxy_candidate_review_ready",
            "station_pre_delineation_review_contract": f"cases/{requested_case_id}/contracts/station_pre_delineation_review.latest.json",
            "station_pre_delineation_review_summary": {
                "review_candidate_count": 1,
                "manual_validation_priority_count": 1,
                "hold_count": 0,
            },
            "pre_delineation_review_status": "manual_validation_priority",
            "station_evidence_search_plan_contract": f"cases/{requested_case_id}/contracts/station_evidence_search_plan.latest.json",
            "station_evidence_search_plan_summary": {
                "plan_count": 1,
                "manual_validation_priority_count": 1,
                "needs_corroboration_count": 1,
            },
            "evidence_search_plan_status": "ready_to_search",
            "station_evidence_findings_contract": f"cases/{requested_case_id}/contracts/station_evidence_findings.latest.json",
            "station_evidence_findings_summary": {
                "finding_count": 2,
                "station_count_with_findings": 1,
                "coordinate_claim_count": 0,
                "hydrography_claim_count": 1,
                "official_source_count": 1,
                "quasi_official_source_count": 1,
                "blocked_promotion_count": 2,
            },
            "evidence_findings_status": "review_only_findings_ready",
            "control_testing_readiness_contract": f"cases/{requested_case_id}/contracts/control_testing_readiness.latest.json",
            "control_testing_readiness_summary": {
                "ready_for": ["pressurized_cascade_control"],
                "not_ready_for": ["watershed_delineation"],
            },
            "control_testing_readiness_status": "ready_for_case_bound_control_testing",
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_load_web_source_session_summary",
        lambda requested_case_id: {
            "present": True,
            "source": "manifest_latest",
            "path": f"cases/{requested_case_id}/contracts/web_source_session.latest.json",
            "status": "downloaded",
            "seed_query_count": 0,
            "seed_url_count": 1,
            "discovered_source_count": 0,
            "download_file_count": 1,
            "needs_web_fetch": False,
            "public_data_inventory_contract": f"cases/{requested_case_id}/contracts/public_data_inventory.latest.json",
            "public_data_summary": {
                "record_count": 1,
                "downloaded_count": 1,
                "blocked_count": 0,
                "available_public_data_kinds": ["dem"],
                "blocked_public_data_kinds": [],
                "status_counts": {"downloaded": 1},
            },
        },
    )
    monkeypatch.setattr(
        run_case_pipeline,
        "_safe_modeling_hints",
        lambda requested_case_id: {
            "case_id": requested_case_id,
            "project_type": "cascade_hydro",
            "workflow_recommendations": {"deferred_stages": [], "stage_activation_guidance": {}},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_case_pipeline.py", "--case-id", case_id, "--phase", "full", "--dry-run"],
    )

    run_case_pipeline.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["missing_inputs"] == ["outlets_empty"]
    assert payload["source_import_session"]["station_topology_contract"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert payload["source_import_session"]["topology_status"] == "named_only"
    assert payload["source_import_session"]["station_geolocation_contract"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"
    assert payload["source_import_session"]["geolocation_status"] == "context_linked"
    assert payload["source_import_session"]["station_geocode_candidates_contract"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    assert payload["source_import_session"]["station_proxy_outlet_anchors_contract"] == f"cases/{case_id}/contracts/station_proxy_outlet_anchors.latest.json"
    assert payload["source_import_session"]["proxy_anchor_status"] == "proxy_review_ready"
    assert payload["source_import_session"]["station_outlet_candidates_contract"] == f"cases/{case_id}/contracts/station_outlet_candidates.latest.json"
    assert payload["source_import_session"]["outlet_candidate_status"] == "proxy_candidate_review_ready"
    assert payload["source_import_session"]["station_pre_delineation_review_contract"] == f"cases/{case_id}/contracts/station_pre_delineation_review.latest.json"
    assert payload["source_import_session"]["pre_delineation_review_status"] == "manual_validation_priority"
    assert payload["source_import_session"]["station_evidence_search_plan_contract"] == f"cases/{case_id}/contracts/station_evidence_search_plan.latest.json"
    assert payload["source_import_session"]["evidence_search_plan_status"] == "ready_to_search"
    assert payload["source_import_session"]["station_evidence_findings_contract"] == f"cases/{case_id}/contracts/station_evidence_findings.latest.json"
    assert payload["source_import_session"]["evidence_findings_status"] == "review_only_findings_ready"
    assert payload["source_import_session"]["control_testing_readiness_contract"] == f"cases/{case_id}/contracts/control_testing_readiness.latest.json"
    assert payload["source_import_session"]["control_testing_readiness_status"] == "ready_for_case_bound_control_testing"
    hint = payload["source_gap_hints"][0]
    assert hint["kind"] == "outlets_empty"
    assert hint["station_topology_contract"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert hint["station_topology_summary"]["station_count"] == 5
    assert hint["topology_status"] == "named_only"
    assert hint["station_geolocation_contract"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"
    assert hint["station_geolocation_summary"]["query_ready_station_count"] == 5
    assert hint["geolocation_status"] == "context_linked"
    assert hint["station_geocode_candidates_contract"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    assert hint["station_proxy_outlet_anchors_contract"] == f"cases/{case_id}/contracts/station_proxy_outlet_anchors.latest.json"
    assert hint["station_proxy_outlet_anchors_summary"]["anchor_count"] == 2
    assert hint["proxy_anchor_status"] == "proxy_review_ready"
    assert hint["station_outlet_candidates_contract"] == f"cases/{case_id}/contracts/station_outlet_candidates.latest.json"
    assert hint["station_outlet_candidates_summary"]["candidate_count"] == 1
    assert hint["outlet_candidate_status"] == "proxy_candidate_review_ready"
    assert hint["station_pre_delineation_review_contract"] == f"cases/{case_id}/contracts/station_pre_delineation_review.latest.json"
    assert hint["station_pre_delineation_review_summary"]["manual_validation_priority_count"] == 1
    assert hint["pre_delineation_review_status"] == "manual_validation_priority"
    assert hint["station_evidence_search_plan_contract"] == f"cases/{case_id}/contracts/station_evidence_search_plan.latest.json"
    assert hint["station_evidence_search_plan_summary"]["plan_count"] == 1
    assert hint["evidence_search_plan_status"] == "ready_to_search"
    assert hint["station_evidence_findings_contract"] == f"cases/{case_id}/contracts/station_evidence_findings.latest.json"
    assert hint["station_evidence_findings_summary"]["finding_count"] == 2
    assert hint["evidence_findings_status"] == "review_only_findings_ready"
    assert hint["control_testing_readiness_contract"] == f"cases/{case_id}/contracts/control_testing_readiness.latest.json"
    assert hint["control_testing_readiness_status"] == "ready_for_case_bound_control_testing"
    assert hint["recommended_public_data"] == ["dem", "landuse", "soil", "hydrography"]
