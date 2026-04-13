from __future__ import annotations

# ruff: noqa: E402

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import import_case_sourcebundle as target


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _resolve_from(root: Path, raw: str | Path) -> Path:
    value = Path(raw)
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _patch_workspace(monkeypatch, root: Path, case_id: str) -> None:
    monkeypatch.setattr(target, "WORKSPACE", root)
    monkeypatch.setattr(target, "resolve_workspace_relpath", lambda raw: _resolve_from(root, raw))
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda requested_case_id: {
            "case_id": requested_case_id,
            "display_name": "Demo Case",
            "scan_dirs": [],
            "sqlite_paths": [],
            "output_dir": "",
        },
    )


def test_import_case_sourcebundle_tracks_case_local_web_inventory_and_sessions(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    web_dir = case_dir / "ingest" / "web"
    downloads_dir = web_dir / "downloads"
    contracts_dir = case_dir / "contracts"

    _patch_workspace(monkeypatch, tmp_path, case_id)
    _write(case_dir / "manifest.yaml", "case:\n  id: demo_case\nlocations:\n  raw_root: cases/demo_case/ingest/raw\n")
    _write(case_dir / "ingest" / "raw" / ".gitkeep", "")
    _write(web_dir / "seed_queries.json", json.dumps({"queries": [{"query": "demo dem"}, {"query": "demo hydrography"}]}, ensure_ascii=False))
    _write(web_dir / "seed_urls.json", json.dumps({"urls": [{"url": "https://example.com/project"}, {"url": "https://example.com/catalog"}]}, ensure_ascii=False))
    _write(
        web_dir / "discovered_urls.json",
        json.dumps(
            {"sources": [{"url": "https://example.com/discovered", "notes": "Hydrography river network basin data"}]},
            ensure_ascii=False,
        ),
    )
    _write(downloads_dir / "project-page.html", "<html><title>Hydropower Cascade Project</title><body>Hydropower cascade station context.</body></html>")
    _write(downloads_dir / "copernicus-dem.html", "<html><title>Copernicus DEM 30 metre dataset</title><body>Digital elevation model terrain coverage.</body></html>")
    _write(
        contracts_dir / "web_fetch_report.latest.json",
        json.dumps(
            {
                "downloaded_count": 2,
                "results": [
                    {
                        "id": "project-page",
                        "url": "https://example.com/project",
                        "kind": "project_context",
                        "status": "downloaded",
                        "path": f"cases/{case_id}/ingest/web/downloads/project-page.html",
                        "content_type": "text/html",
                    },
                    {
                        "id": "copernicus-dem",
                        "url": "https://example.com/catalog",
                        "kind": "dem_catalog",
                        "status": "downloaded",
                        "path": f"cases/{case_id}/ingest/web/downloads/copernicus-dem.html",
                        "content_type": "text/html",
                    },
                    {
                        "id": "hydrography",
                        "url": "https://example.com/discovered",
                        "kind": "hydrography",
                        "status": "http_error",
                        "http_status": 403,
                    },
                ],
            },
            ensure_ascii=False,
        ),
    )

    result = target.import_case_sourcebundle(case_id)

    assert result["ok"] is True
    assert result["source_mode"] == "synthesized"
    assert result["web_fetch_report_contract"] == f"cases/{case_id}/contracts/web_fetch_report.latest.json"
    assert result["web_source_session_contract"] == f"cases/{case_id}/contracts/web_source_session.latest.json"
    assert result["public_data_inventory_contract"] == f"cases/{case_id}/contracts/public_data_inventory.latest.json"

    bundle = json.loads((contracts_dir / "source_bundle.contract.json").read_text(encoding="utf-8"))
    records = bundle["records"]
    metadata_roles = {
        (record.get("artifact") or {}).get("metadata", {}).get("role_in_bundle")
        for record in records
    }
    artifact_paths = {
        (record.get("artifact") or {}).get("path")
        for record in records
    }
    assert {"raw_root", "web_seed", "web_download", "web_fetch_report", "public_data_inventory"}.issubset(metadata_roles)
    assert str((case_dir / "ingest" / "raw").resolve()) in artifact_paths
    assert str((web_dir / "seed_queries.json").resolve()) in artifact_paths
    assert str((downloads_dir / "project-page.html").resolve()) in artifact_paths
    assert str((downloads_dir / "copernicus-dem.html").resolve()) in artifact_paths

    import_session = json.loads((contracts_dir / "source_import_session.latest.json").read_text(encoding="utf-8"))
    assert import_session["inputs"]["scan_dirs"] == [
        f"cases/{case_id}/ingest/raw",
        f"cases/{case_id}/ingest/web",
    ]
    assert import_session["inputs"]["web_seed_files"] == [
        f"cases/{case_id}/ingest/web/discovered_urls.json",
        f"cases/{case_id}/ingest/web/seed_queries.json",
        f"cases/{case_id}/ingest/web/seed_urls.json",
    ]
    assert import_session["inputs"]["web_download_files"] == [
        f"cases/{case_id}/ingest/web/downloads/copernicus-dem.html",
        f"cases/{case_id}/ingest/web/downloads/project-page.html",
    ]
    assert import_session["inputs"]["web_source_session"] == f"cases/{case_id}/contracts/web_source_session.latest.json"
    assert import_session["inputs"]["public_data_inventory"] == f"cases/{case_id}/contracts/public_data_inventory.latest.json"

    public_data_inventory = json.loads((contracts_dir / "public_data_inventory.latest.json").read_text(encoding="utf-8"))
    summary = public_data_inventory["summary"]
    records = public_data_inventory["records"]
    blocked_sources = public_data_inventory["blocked_sources"]
    assert summary["record_count"] == len(records)
    assert summary["downloaded_count"] == 2
    assert summary["blocked_count"] == len(blocked_sources) == 1
    assert summary["available_public_data_kinds"] == ["dem", "project_context"]
    assert summary["blocked_public_data_kinds"] == ["hydrography"]
    assert summary["status_counts"] == {"downloaded": 2, "http_error": 1}
    assert not (set(summary["available_public_data_kinds"]) & set(summary["blocked_public_data_kinds"]))
    assert sum(1 for record in records if record["signals"]["fetch_status"] == "downloaded") == summary["downloaded_count"]
    assert public_data_inventory["fetch_report_contract"] == f"cases/{case_id}/contracts/web_fetch_report.latest.json"
    assert public_data_inventory["web_source_session_contract"] == f"cases/{case_id}/contracts/web_source_session.latest.json"
    assert [record["source_id"] for record in records] == ["project-page", "copernicus-dem", "hydrography"]
    assert records[0]["public_data_kind"] == "project_context"
    assert records[1]["public_data_kind"] == "dem"
    assert records[2]["public_data_kind"] == "hydrography"
    assert records[2]["path"] is None
    assert len(blocked_sources) == 1
    assert blocked_sources[0]["source_id"] == "hydrography"

    web_session = json.loads((contracts_dir / "web_source_session.latest.json").read_text(encoding="utf-8"))
    assert web_session["status"] == "downloaded"
    assert web_session["seed_query_count"] == 2
    assert web_session["seed_url_count"] == 2
    assert web_session["discovered_source_count"] == 1
    assert web_session["download_file_count"] == 2
    assert web_session["downloaded_count"] == 2
    assert web_session["needs_web_fetch"] is False
    assert web_session["fetch_report_contract"] == f"cases/{case_id}/contracts/web_fetch_report.latest.json"
    assert web_session["public_data_inventory_contract"] == f"cases/{case_id}/contracts/public_data_inventory.latest.json"
    assert web_session["public_data_summary"]["available_public_data_kinds"] == ["dem", "project_context"]
    assert web_session["public_data_summary"]["blocked_public_data_kinds"] == ["hydrography"]
    assert web_session["public_data_summary"]["status_counts"] == {"downloaded": 2, "http_error": 1}

    manifest = yaml.safe_load((case_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["latest_source_import_session"]["path"] == f"cases/{case_id}/contracts/source_import_session.latest.json"
    assert manifest["latest_web_source_session"]["path"] == f"cases/{case_id}/contracts/web_source_session.latest.json"
    assert manifest["latest_web_source_session"]["status"] == "downloaded"


def test_import_case_sourcebundle_marks_seeded_web_sessions_when_fetch_still_pending(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    web_dir = case_dir / "ingest" / "web"
    contracts_dir = case_dir / "contracts"

    _patch_workspace(monkeypatch, tmp_path, case_id)
    _write(case_dir / "manifest.yaml", "case:\n  id: demo_case\n")
    _write(case_dir / "ingest" / "raw" / ".gitkeep", "")
    _write(web_dir / "seed_queries.json", json.dumps({"queries": [{"query": "demo dem"}]}, ensure_ascii=False))
    _write(web_dir / "seed_urls.json", json.dumps({"urls": [{"url": "https://example.com/project"}]}, ensure_ascii=False))

    result = target.import_case_sourcebundle(case_id)

    assert result["ok"] is True
    assert result["web_fetch_report_contract"] is None
    assert result["web_source_session_contract"] == f"cases/{case_id}/contracts/web_source_session.latest.json"
    assert result["public_data_inventory_contract"] is None

    web_session = json.loads((contracts_dir / "web_source_session.latest.json").read_text(encoding="utf-8"))
    assert web_session["status"] == "seeded"
    assert web_session["seed_query_count"] == 1
    assert web_session["seed_url_count"] == 1
    assert web_session["discovered_source_count"] == 0
    assert web_session["download_file_count"] == 0
    assert web_session["downloaded_count"] == 0
    assert web_session["needs_web_fetch"] is True
    assert web_session["fetch_report_contract"] is None

    bundle = json.loads((contracts_dir / "source_bundle.contract.json").read_text(encoding="utf-8"))
    metadata_roles = [
        (record.get("artifact") or {}).get("metadata", {}).get("role_in_bundle")
        for record in bundle["records"]
    ]
    assert metadata_roles.count("web_seed") == 2
    assert "web_download" not in metadata_roles
    assert "web_fetch_report" not in metadata_roles
