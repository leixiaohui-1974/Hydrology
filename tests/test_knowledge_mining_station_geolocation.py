from __future__ import annotations

import json
from pathlib import Path

from hydro_model import knowledge_mining as target


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_normalize_uses_station_geolocation_as_review_fallback(tmp_path: Path) -> None:
    case_id = "demo_case"
    output_dir = tmp_path / "cases" / case_id / "source_selection" / "product_outputs"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        output_dir / "source_reliability.json",
        {
            "case_id": case_id,
            "stage": "score",
            "candidates": [],
            "best_per_station": {},
        },
    )
    _write_json(
        output_dir / "coordinate_validation.json",
        {
            "case_id": case_id,
            "stage": "validate",
            "anomalies": [],
        },
    )
    _write_json(
        contracts_dir / "station_geolocation.latest.json",
        {
            "case_id": case_id,
            "schema_version": "station_geolocation.v1",
            "geolocation_status": "context_linked",
            "stations": [
                {
                    "station_id": "S01",
                    "canonical_name": "墨脱水电站",
                    "geolocation_status": "context_linked",
                    "query_candidates": [
                        "墨脱水电站 经纬度",
                        "墨脱水电站 坐标",
                    ],
                    "context_evidence_refs": [
                        {
                            "source_id": "project-news",
                            "url": "https://example.com/project-news",
                            "path": f"cases/{case_id}/ingest/web/downloads/project-news.html",
                        }
                    ],
                    "blocked_public_data_kinds": ["hydrography"],
                }
            ],
        },
    )

    config = {
        "case_id": case_id,
        "target_stations": ["墨脱水电站"],
        "output_dir": str(output_dir),
    }

    payload = target.normalize(config)

    mapping = payload["mapping"]["mappings"][0]
    assert mapping["name"] == "墨脱水电站"
    assert mapping["status"] == "context_linked"
    assert mapping["geolocation_status"] == "context_linked"
    assert mapping["query_candidates"] == ["墨脱水电站 经纬度", "墨脱水电站 坐标"]
    assert mapping["evidence_count"] == 1
    assert mapping["blocked_public_data_kinds"] == ["hydrography"]

    ready = payload["delineation_ready"]
    assert ready["count"] == 0
    assert ready["excluded"] == ["墨脱水电站"]
    assert ready["review_candidates"][0]["name"] == "墨脱水电站"
    assert ready["normalization_inputs"]["station_geolocation_status"] == "context_linked"
    assert "station geolocation and proxy anchor evidence" in ready["notes"]


def test_normalize_promotes_station_proxy_anchor_links_without_fake_outlets(tmp_path: Path) -> None:
    case_id = "demo_case"
    output_dir = tmp_path / "cases" / case_id / "source_selection" / "product_outputs"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        output_dir / "source_reliability.json",
        {
            "case_id": case_id,
            "stage": "score",
            "candidates": [],
            "best_per_station": {},
        },
    )
    _write_json(
        output_dir / "coordinate_validation.json",
        {
            "case_id": case_id,
            "stage": "validate",
            "anomalies": [],
        },
    )
    _write_json(
        contracts_dir / "station_geolocation.latest.json",
        {
            "case_id": case_id,
            "schema_version": "station_geolocation.v1",
            "geolocation_status": "candidate_augmented",
            "stations": [
                {
                    "station_id": "YJ01",
                    "canonical_name": "墨脱水电站",
                    "geolocation_status": "candidate_augmented",
                    "query_candidates": ["墨脱 经纬度"],
                    "context_evidence_refs": [],
                    "blocked_public_data_kinds": ["hydrography"],
                }
            ],
        },
    )
    _write_json(
        contracts_dir / "station_proxy_outlet_anchors.latest.json",
        {
            "case_id": case_id,
            "schema_version": "station_proxy_outlet_anchors.v1",
            "anchor_status": "proxy_review_ready",
            "station_proxy_anchors": [
                {
                    "anchor_id": f"{case_id}-proxy-anchor-01",
                    "station_id": "YJ01",
                    "station_name": "墨脱水电站",
                    "proxy_anchor_status": "proxy_review_ready",
                    "anchor_kind": "proxy_locality",
                    "confidence": "low",
                    "lat": 29.3,
                    "lon": 95.3,
                    "display_name": "墨脱县, 墨脱镇, 墨脱县, 林芝市, 西藏自治区, 中国",
                }
            ],
            "unassigned_case_proxy_anchors": [
                {
                    "anchor_id": f"{case_id}-proxy-anchor-02",
                    "label": "米林水电站坝址",
                }
            ],
        },
    )

    config = {
        "case_id": case_id,
        "target_stations": ["墨脱水电站", "多雄藏布水电站"],
        "output_dir": str(output_dir),
    }

    payload = target.normalize(config)

    mapping_by_name = {row["name"]: row for row in payload["mapping"]["mappings"]}
    assert mapping_by_name["墨脱水电站"]["status"] == "proxy_anchor_linked"
    assert mapping_by_name["墨脱水电站"]["proxy_anchor_ref"] == f"{case_id}-proxy-anchor-01"
    assert mapping_by_name["多雄藏布水电站"]["status"] == "missing"
    ready = payload["delineation_ready"]
    assert ready["count"] == 0
    assert ready["proxy_anchor_candidates"][0]["label"] == "米林水电站坝址"
    assert ready["normalization_inputs"]["station_proxy_outlet_anchor_status"] == "proxy_review_ready"
