from __future__ import annotations

import json
import sys
from pathlib import Path

import workflows.run_case_pipeline as run_case_pipeline


def test_run_case_pipeline_dry_run_surfaces_public_data_inventory_summary(
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
    assert payload["missing_inputs"] == ["outlets_empty"]
    assert payload["web_source_session"]["public_data_inventory_contract"] == "cases/demo_case/contracts/public_data_inventory.latest.json"
    assert payload["web_source_session"]["public_data_summary"]["blocked_public_data_kinds"] == ["hydrography"]
    assert payload["source_gap_hints"][0]["public_data_inventory_contract"] == "cases/demo_case/contracts/public_data_inventory.latest.json"
    assert payload["source_gap_hints"][0]["public_data_summary"]["blocked_count"] == 1
    assert payload["source_gap_hints"][0]["recommended_public_data"] == ["dem", "landuse", "soil", "hydrography"]
