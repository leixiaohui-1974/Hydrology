import json
import sys
from pathlib import Path

from workflows import run_case_pipeline


def test_run_case_pipeline_dry_run_surfaces_public_data_inventory_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    case_id = "demo_case"
    manifest_path = tmp_path / "cases" / case_id / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("case:\n  id: demo_case\n", encoding="utf-8")
    outlets_path = tmp_path / "cases" / case_id / "contracts" / "outlets.normalized.json"
    outlets_path.parent.mkdir(parents=True, exist_ok=True)
    outlets_path.write_text(json.dumps({"count": 0, "outlets": []}), encoding="utf-8")

    monkeypatch.setattr(run_case_pipeline, "import_case_sourcebundle", lambda requested_case_id: {"ok": True, "case_id": requested_case_id})
    monkeypatch.setattr(
        run_case_pipeline,
        "resolve_case_entry_inputs",
        lambda *args, **kwargs: {
            "case_manifest": str(manifest_path),
            "source_bundle_json": str(tmp_path / "cases" / case_id / "contracts" / "source_bundle.contract.json"),
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
            "record_count": 4,
            "imported_at": "2026-04-13T00:00:00+00:00",
            "scan_dirs": [f"cases/{requested_case_id}/ingest/raw"],
            "web_seed_files": [f"cases/{requested_case_id}/ingest/web/seed_urls.json"],
            "sqlite_import_reason": "skipped",
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
    hint = payload["source_gap_hints"][0]
    assert hint["public_data_inventory_contract"] == f"cases/{case_id}/contracts/public_data_inventory.latest.json"
    assert hint["public_data_summary"]["available_public_data_kinds"] == ["dem"]
    assert hint["public_data_summary"]["record_count"] == 1

