from __future__ import annotations

import json
from pathlib import Path

import fetch_case_station_geocode_candidates as target


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_fetch_case_station_geocode_candidates_writes_review_contract(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        contracts_dir / "station_geolocation.latest.json",
        {
            "case_id": case_id,
            "stations": [
                {
                    "station_id": "S01",
                    "canonical_name": "墨脱水电站",
                    "query_candidates": ["墨脱水电站 经纬度"],
                }
            ],
            "case_context": {
                "mainstem_planning_hints": [
                    {
                        "hint_id": "milin_hint",
                        "label": "米林水电站坝址",
                        "query_candidates": ["米林市"],
                    }
                ]
            },
        },
    )

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(
        target,
        "load_case_config",
        lambda requested_case_id: {
            "case_id": requested_case_id,
            "validation": {"lat_range": [28.0, 31.0], "lon_range": [93.0, 97.0]},
        },
    )
    monkeypatch.setattr(
        target,
        "_search_nominatim",
        lambda query, cfg, limit: [
            {
                "place_id": 1,
                "osm_type": "relation",
                "osm_id": 2,
                "name": "米林市",
                "display_name": "米林市, 林芝市, 西藏自治区, 中国",
                "lat": "29.2177863",
                "lon": "94.2139880",
                "category": "boundary",
                "type": "administrative",
                "importance": 0.43,
            }
        ]
        if query == "米林市"
        else [],
    )

    payload = target.fetch_case_station_geocode_candidates(case_id, limit=2)

    assert payload["schema_version"] == "station_geocode_candidates.v1"
    assert payload["summary"]["query_count"] == 2
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["owners_with_candidates"] == 1
    assert payload["summary"]["review_anchor_candidate_count"] == 1
    assert payload["summary"]["owners_with_review_anchors"] == 1
    assert payload["owners"] == [
        {"owner_kind": "station", "label": "墨脱水电站", "owner_id": "S01", "query_count": 1, "candidate_count": 0, "selected_anchor_candidate_count": 0},
        {"owner_kind": "hint", "label": "米林水电站坝址", "owner_id": "milin_hint", "query_count": 1, "candidate_count": 1, "selected_anchor_candidate_count": 1},
    ]
    result_rows = {row["owner_id"]: row for row in payload["results"]}
    assert result_rows["S01"]["candidate_count"] == 0
    assert result_rows["milin_hint"]["candidates"][0]["name"] == "米林市"
    assert result_rows["milin_hint"]["selected_anchor_candidates"][0]["anchor_signals"]["proxy_class"] == "admin_area_proxy"
    assert payload["review_anchor_candidates"][0]["owner_id"] == "milin_hint"
    assert (contracts_dir / "station_geocode_candidates.latest.json").is_file()
