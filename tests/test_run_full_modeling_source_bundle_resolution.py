from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows import run_full_modeling as target


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_resolve_source_bundle_path_prefers_authoritative_bundle_with_usable_dem(
    monkeypatch, tmp_path: Path
) -> None:
    case_id = "daduhe"
    case_dir = tmp_path / "cases" / case_id
    case_bundle = case_dir / "contracts" / "source_bundle.contract.json"
    external_bundle = (
        tmp_path
        / "pipedream-hydrology-integration-lab"
        / "research"
        / "e2e_reports"
        / case_id
        / "contracts"
        / "source_bundle.contract.json"
    )
    case_dem_path = case_dir / "contracts" / "dem_case.tif"
    case_dem_path.parent.mkdir(parents=True, exist_ok=True)
    case_dem_path.write_text("stub", encoding="utf-8")
    authoritative_dem_path = tmp_path / "authoritative_dem.tif"
    authoritative_dem_path.write_text("stub", encoding="utf-8")

    _write_json(
        case_bundle,
        {
            "records": [
                {
                    "role": "dem_primary",
                    "artifact": {"path": f"cases/{case_id}/contracts/dem_case.tif"},
                }
            ]
        },
    )
    _write_json(
        external_bundle,
        {
            "records": [
                {
                    "role": "dem_authoritative",
                    "artifact": {"path": str(authoritative_dem_path)},
                }
            ]
        },
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    resolved = target._resolve_source_bundle_path(case_dir, case_id)

    assert resolved == external_bundle


def test_resolve_source_bundle_path_falls_back_to_external_when_case_bundle_has_no_usable_dem(
    monkeypatch, tmp_path: Path
) -> None:
    case_id = "daduhe"
    case_dir = tmp_path / "cases" / case_id
    case_bundle = case_dir / "contracts" / "source_bundle.contract.json"
    external_bundle = (
        tmp_path
        / "pipedream-hydrology-integration-lab"
        / "research"
        / "e2e_reports"
        / case_id
        / "contracts"
        / "source_bundle.contract.json"
    )
    dem_path = tmp_path / "external_dem.tif"
    dem_path.write_text("stub", encoding="utf-8")

    _write_json(case_bundle, {"records": [{"role": "wxq_model_1"}]})
    _write_json(
        external_bundle,
        {
            "records": [
                {
                    "role": "dem_fallback",
                    "artifact": {"path": str(dem_path)},
                }
            ]
        },
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    resolved = target._resolve_source_bundle_path(case_dir, case_id)

    assert resolved == external_bundle


def test_resolve_source_bundle_path_falls_back_to_existing_external_when_case_bundle_missing(
    monkeypatch, tmp_path: Path
) -> None:
    case_id = "daduhe"
    case_dir = tmp_path / "cases" / case_id
    external_bundle = (
        tmp_path
        / "pipedream-hydrology-integration-lab"
        / "research"
        / "e2e_reports"
        / case_id
        / "contracts"
        / "source_bundle.contract.json"
    )
    _write_json(external_bundle, {"records": [{"role": "wxq_model_1"}]})

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    resolved = target._resolve_source_bundle_path(case_dir, case_id)

    assert resolved == external_bundle
