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


def test_persisted_raw_path_falls_back_to_absolute_when_resolve_loops(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    output_dir = tmp_path / "cases" / case_id / "source_selection" / "product_outputs"
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "resolve_workspace_relpath", lambda raw: output_dir)

    original_resolve = output_dir.__class__.resolve

    def fake_resolve(self: Path, *args, **kwargs) -> Path:
        if self == output_dir:
            raise RuntimeError("Symlink loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(output_dir.__class__, "resolve", fake_resolve)

    assert target._persisted_raw_path_or_none(str(output_dir)) == (
        f"cases/{case_id}/source_selection/product_outputs"
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
    assert f"cases/{case_id}/ingest/raw" in artifact_paths
    assert f"cases/{case_id}/ingest/web/seed_queries.json" in artifact_paths
    assert f"cases/{case_id}/ingest/web/downloads/project-page.html" in artifact_paths
    assert f"cases/{case_id}/ingest/web/downloads/copernicus-dem.html" in artifact_paths

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


def test_import_case_sourcebundle_writes_station_topology_contract_from_yaml_sources(
    monkeypatch, tmp_path: Path
) -> None:
    case_id = "yjdt"
    case_dir = tmp_path / "cases" / case_id
    contracts_dir = case_dir / "contracts"
    incoming_dir = tmp_path / "incoming"
    engine_path = tmp_path / "YJDT" / "src" / "yjdt" / "config" / "yajiang_bigbend_params.yaml"
    scheme_path = tmp_path / "YJDT" / "src" / "yjdt" / "config" / "yajiang_params.yaml"

    _patch_workspace(monkeypatch, tmp_path, case_id)
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda requested_case_id: {
            "case_id": requested_case_id,
            "display_name": "YJDT",
            "project_type": "cascade_hydro",
            "scan_dirs": [],
            "sqlite_paths": [],
            "output_dir": "",
        },
    )

    _write(
        case_dir / "manifest.yaml",
        "case:\n  id: yjdt\nlatest_source_bundle:\n  path: incoming/source_bundle.contract.json\n",
    )
    _write(
        engine_path,
        """
cascade_stations:
  - id: "YJ01"
    name: "墨脱水电站"
    name_en: "Medog Hydropower Station"
    position: 1
    hydraulic:
      rated_head: 480.0
      min_head: 450.0
      max_head: 510.0
      rated_flow: 210.0
      tunnel_length: 25000.0
      tunnel_diameter: 11.0
      wave_speed: 1350.0
      friction_factor: 0.015
      water_inertia_time: 12.0
    turbine:
      type: "francis"
      num_units: 6
      rated_power: 1000.0
      rated_speed: 166.7
      efficiency: 0.94
    generator:
      type: "synchronous"
      rated_power: 1111.0
      rated_voltage: 20.0
      power_factor: 0.9
      inertia_constant: 4.0
    governor:
      type: "PID"
      kp: 2.5
      ki: 0.15
      kd: 4.0
      rate_limit: 0.1
odd_config:
  system_boundaries:
    pressure:
      optimal_min: 4.5
  transient_boundaries:
    max_simultaneous_actions: 2
  cascade_boundaries:
    cascade_protection_enabled: true
""".strip(),
    )
    _write(
        scheme_path,
        """
cascade_config:
  stations:
    - id: "YJ01"
      name: "墨脱水电站"
      position: 1
      installed_capacity: 6000
      num_units: 6
      scheme: "scheme_realistic"
""".strip(),
    )
    incoming_dir.mkdir(parents=True, exist_ok=True)
    _write(
        incoming_dir / "source_bundle.contract.json",
        json.dumps(
            {
                "case_id": case_id,
                "records": [
                    {
                        "role": "yjdt_engine_params",
                        "artifact": {
                            "artifact_type": "yaml",
                            "path": "YJDT/src/yjdt/config/yajiang_bigbend_params.yaml",
                            "metadata": {"role_in_bundle": "external_model_params"},
                        },
                    },
                    {
                        "role": "yjdt_scheme_params",
                        "artifact": {
                            "artifact_type": "yaml",
                            "path": "YJDT/src/yjdt/config/yajiang_params.yaml",
                            "metadata": {"role_in_bundle": "external_model_scheme"},
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
    )

    result = target.import_case_sourcebundle(case_id)

    assert result["station_topology_contract"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert result["station_geolocation_contract"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"
    bundle = json.loads((contracts_dir / "source_bundle.contract.json").read_text(encoding="utf-8"))
    assert any(
        (record.get("artifact") or {}).get("metadata", {}).get("role_in_bundle") == "station_topology"
        for record in bundle["records"]
    )
    assert any(
        (record.get("artifact") or {}).get("metadata", {}).get("role_in_bundle") == "station_geolocation"
        for record in bundle["records"]
    )

    station_topology = json.loads((contracts_dir / "station_topology.latest.json").read_text(encoding="utf-8"))
    assert station_topology["topology_status"] == "named_only"
    assert station_topology["summary"]["station_count"] == 1
    assert station_topology["summary"]["geo_located_station_count"] == 0
    assert station_topology["stations"][0]["station_id"] == "YJ01"
    assert station_topology["stations"][0]["aliases"] == ["Medog Hydropower Station"]
    assert station_topology["stations"][0]["installed_capacity_mw"] == 6000
    assert station_topology["stations"][0]["geometry_status"] == "missing"

    import_session = json.loads((contracts_dir / "source_import_session.latest.json").read_text(encoding="utf-8"))
    assert import_session["station_topology_contract"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert import_session["station_topology_summary"]["station_count"] == 1
    assert import_session["topology_status"] == "named_only"
    assert import_session["inputs"]["station_topology"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert import_session["station_geolocation_contract"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"
    assert import_session["station_geolocation_summary"]["station_count"] == 1
    assert import_session["geolocation_status"] == "query_ready"
    assert import_session["inputs"]["station_geolocation"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"

    station_geolocation = json.loads((contracts_dir / "station_geolocation.latest.json").read_text(encoding="utf-8"))
    assert station_geolocation["geolocation_status"] == "query_ready"
    assert station_geolocation["summary"]["station_count"] == 1
    assert station_geolocation["summary"]["geo_located_station_count"] == 0
    assert station_geolocation["stations"][0]["station_id"] == "YJ01"
    assert station_geolocation["stations"][0]["query_candidates"][0] == "墨脱水电站 经纬度"
    assert station_geolocation["stations"][0]["resolved_coordinate"] is None

    manifest = yaml.safe_load((case_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["latest_station_topology"]["path"] == f"cases/{case_id}/contracts/station_topology.latest.json"
    assert manifest["latest_station_topology"]["status"] == "named_only"
    assert manifest["latest_station_geolocation"]["path"] == f"cases/{case_id}/contracts/station_geolocation.latest.json"
    assert manifest["latest_station_geolocation"]["status"] == "query_ready"


def test_import_case_sourcebundle_prefers_product_output_outlets_when_refreshing_canonical_contract(
    monkeypatch, tmp_path: Path
) -> None:
    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    contracts_dir = case_dir / "contracts"
    product_outputs = case_dir / "source_selection" / "product_outputs"
    incoming_dir = tmp_path / "incoming"

    _patch_workspace(monkeypatch, tmp_path, case_id)
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda requested_case_id: {
            "case_id": requested_case_id,
            "display_name": "Demo Case",
            "project_type": "cascade_hydro",
            "scan_dirs": [],
            "sqlite_paths": [],
            "output_dir": f"cases/{case_id}/source_selection/product_outputs",
        },
    )

    _write(
        case_dir / "manifest.yaml",
        "case:\n  id: demo_case\nlatest_source_bundle:\n  path: incoming/source_bundle.contract.json\nlatest_outlets:\n  path: cases/demo_case/contracts/outlets.normalized.json\n",
    )
    incoming_dir.mkdir(parents=True, exist_ok=True)
    _write(
        incoming_dir / "source_bundle.contract.json",
        json.dumps({"case_id": case_id, "records": []}, ensure_ascii=False),
    )
    _write(
        contracts_dir / "outlets.normalized.json",
        json.dumps({"count": 0, "outlets": [], "notes": "stale"}, ensure_ascii=False),
    )
    _write(
        product_outputs / "outlets.delineation_ready.json",
        json.dumps(
            {
                "case_id": case_id,
                "workflow": "watershed_delineation",
                "filter_rules": ["score >= 0.7"],
                "excluded": ["墨脱水电站"],
                "count": 0,
                "outlets": [],
                "review_candidates": [
                    {
                        "name": "墨脱水电站",
                        "geolocation_status": "context_linked",
                        "query_candidates": ["墨脱水电站 经纬度"],
                    }
                ],
                "normalization_inputs": {
                    "station_geolocation_contract": f"cases/{case_id}/contracts/station_geolocation.latest.json",
                    "station_geolocation_status": "context_linked",
                },
                "notes": "No delineation-ready outlets yet; station_geolocation evidence is available for review-driven coordinate resolution.",
            },
            ensure_ascii=False,
        ),
    )

    result = target.import_case_sourcebundle(case_id)

    assert result["outlets_input"] == f"cases/{case_id}/source_selection/product_outputs/outlets.delineation_ready.json"
    canonical_outlets = json.loads((contracts_dir / "outlets.normalized.json").read_text(encoding="utf-8"))
    assert canonical_outlets["generated_from"] == f"cases/{case_id}/source_selection/product_outputs/outlets.delineation_ready.json"
    assert canonical_outlets["review_required"] is True
    assert canonical_outlets["review_candidates"][0]["name"] == "墨脱水电站"
    assert canonical_outlets["normalization_inputs"]["station_geolocation_status"] == "context_linked"


def test_import_case_sourcebundle_tracks_station_geocode_candidates_contract(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    contracts_dir = case_dir / "contracts"
    raw_dir = case_dir / "ingest" / "raw"
    incoming_dir = tmp_path / "incoming"
    configs_dir = tmp_path / "Hydrology" / "configs"

    _patch_workspace(monkeypatch, tmp_path, case_id)
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

    _write(case_dir / "manifest.yaml", "case:\n  id: demo_case\nlatest_source_bundle:\n  path: incoming/source_bundle.contract.json\n")
    raw_dir.mkdir(parents=True, exist_ok=True)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    _write(
        configs_dir / f"{case_id}.yaml",
        "project_type: cascade_hydro\ntopology:\n  system_type: pressurized_cascade\n",
    )
    _write(contracts_dir / "control_optimization_report.json", json.dumps({"status": "ready", "metrics": {"control_score": 0.97, "scheduling_score": 0.97}}, ensure_ascii=False))
    _write(contracts_dir / "sil_verification_report.json", json.dumps({"status": "ready", "metrics": {"sil_score": 0.7}}, ensure_ascii=False))
    _write(contracts_dir / "odd_coverage_report.json", json.dumps({"coverage_metrics": {"total_scenarios_tested": 10}}, ensure_ascii=False))
    _write(contracts_dir / "outlets.normalized.json", json.dumps({"count": 0}, ensure_ascii=False))
    _write(incoming_dir / "source_bundle.contract.json", json.dumps({"case_id": case_id, "records": []}, ensure_ascii=False))
    _write(
        contracts_dir / "station_topology.latest.json",
        json.dumps(
            {
                "case_id": case_id,
                "schema_version": "station_topology.v1",
                "stations": [
                    {
                        "station_id": "S01",
                        "canonical_name": "演示电站",
                        "aliases": [],
                        "cascade_position": 1,
                        "source_refs": [],
                    }
                ],
                "summary": {"station_count": 1},
                "topology_status": "named_only",
            },
            ensure_ascii=False,
        ),
    )
    _write(
        contracts_dir / "station_geocode_candidates.latest.json",
        json.dumps(
            {
                "case_id": case_id,
                "summary": {"candidate_count": 1},
                "review_anchor_candidates": [
                    {
                        "owner_kind": "hint",
                        "owner_id": "demo_hint",
                        "label": "演示锚点",
                        "query": "演示电站",
                        "candidate": {
                            "name": "演示电站镇",
                            "display_name": "演示电站镇, 演示市, 中国",
                            "lat": 29.2,
                            "lon": 94.2,
                            "category": "boundary",
                            "type": "administrative",
                            "anchor_score": 2.8,
                            "anchor_signals": {"proxy_class": "admin_area_proxy"},
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    _write(
        raw_dir / "station_naming_evidence.json",
        json.dumps(
            {
                "case_id": case_id,
                "mainstem_planning_hints": [
                    {
                        "hint_id": "role_hint",
                        "kind": "role_hypothesis",
                        "stations": [
                            {"name": "演示电站", "role_hypothesis": "tunnel-system", "confidence": "high"}
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    _write(
        raw_dir / "station_evidence_findings.json",
        json.dumps(
            {
                "case_id": case_id,
                "station_findings": [
                    {
                        "finding_id": "f1",
                        "station_id": "S01",
                        "station_name": "演示电站",
                        "source_attribution": {"source_url": "https://example.com", "publisher_tier": "official"},
                        "claims": [{"claim_type": "dam_site_text", "claim_value": "演示站"}],
                        "promotion_guardrails": {"promotion_blockers": ["review_only"]},
                    }
                ],
                "unassigned_findings": [],
            },
            ensure_ascii=False,
        ),
    )

    result = target.import_case_sourcebundle(case_id)

    assert result["station_geocode_candidates_contract"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    payload = json.loads((contracts_dir / "source_bundle.contract.json").read_text(encoding="utf-8"))
    assert any(
        (record.get("artifact") or {}).get("metadata", {}).get("role_in_bundle") == "station_geocode_candidates"
        for record in payload["records"]
    )
    session = json.loads((contracts_dir / "source_import_session.latest.json").read_text(encoding="utf-8"))
    assert session["station_geocode_candidates_contract"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    assert session["inputs"]["station_geocode_candidates"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    assert session["geolocation_status"] == "candidate_augmented"
    assert session["station_proxy_outlet_anchors_contract"] == f"cases/{case_id}/contracts/station_proxy_outlet_anchors.latest.json"
    assert session["proxy_anchor_status"] == "proxy_review_ready"
    assert session["station_outlet_candidates_contract"] == f"cases/{case_id}/contracts/station_outlet_candidates.latest.json"
    assert session["outlet_candidate_status"] == "proxy_candidate_review_ready"
    assert session["station_pre_delineation_review_contract"] == f"cases/{case_id}/contracts/station_pre_delineation_review.latest.json"
    assert session["pre_delineation_review_status"] == "manual_validation_priority"
    assert session["station_evidence_search_plan_contract"] == f"cases/{case_id}/contracts/station_evidence_search_plan.latest.json"
    assert session["evidence_search_plan_status"] == "ready_to_search"
    assert session["station_evidence_findings_contract"] == f"cases/{case_id}/contracts/station_evidence_findings.latest.json"
    assert session["evidence_findings_status"] == "review_only_findings_ready"
    assert session["control_testing_readiness_contract"] == f"cases/{case_id}/contracts/control_testing_readiness.latest.json"
    assert session["control_testing_readiness_status"] == "ready_for_case_bound_control_testing"
    manifest = yaml.safe_load((case_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["latest_station_geocode_candidates"]["path"] == f"cases/{case_id}/contracts/station_geocode_candidates.latest.json"
    assert manifest["latest_station_proxy_outlet_anchors"]["path"] == f"cases/{case_id}/contracts/station_proxy_outlet_anchors.latest.json"
    assert manifest["latest_station_outlet_candidates"]["path"] == f"cases/{case_id}/contracts/station_outlet_candidates.latest.json"
    assert manifest["latest_station_pre_delineation_review"]["path"] == f"cases/{case_id}/contracts/station_pre_delineation_review.latest.json"
    assert manifest["latest_station_evidence_search_plan"]["path"] == f"cases/{case_id}/contracts/station_evidence_search_plan.latest.json"
    assert manifest["latest_station_evidence_findings"]["path"] == f"cases/{case_id}/contracts/station_evidence_findings.latest.json"
    assert manifest["latest_control_testing_readiness"]["path"] == f"cases/{case_id}/contracts/control_testing_readiness.latest.json"
