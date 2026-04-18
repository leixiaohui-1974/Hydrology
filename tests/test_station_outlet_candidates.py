from __future__ import annotations

import json
from pathlib import Path

from scripts.station_outlet_candidates import build_station_outlet_candidates


def test_build_station_outlet_candidates_from_station_proxy_anchors(tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    raw_dir = tmp_path / "cases" / case_id / "ingest" / "raw"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "station_proxy_outlet_anchors.latest.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "station_proxy_anchors": [
                    {
                        "anchor_id": "demo-anchor-01",
                        "station_id": "YJ01",
                        "station_name": "墨脱水电站",
                        "proxy_anchor_status": "proxy_review_ready",
                        "anchor_kind": "proxy_locality",
                        "confidence": "low",
                        "lat": 29.3,
                        "lon": 95.3,
                        "display_name": "墨脱县, 墨脱镇, 墨脱县, 林芝市, 中国",
                        "source_name": "墨脱县",
                        "source_type": "city",
                        "source_category": "place",
                        "mapping_basis": "query_token_matches_engineering_station_name",
                        "limitations": ["proxy_only_not_authoritative_outlet"],
                    }
                ],
                "unassigned_case_proxy_anchors": [
                    {"anchor_id": "demo-anchor-02", "label": "米林水电站坝址"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (raw_dir / "station_naming_evidence.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "mainstem_planning_hints": [
                    {
                        "hint_id": "role_hint",
                        "kind": "role_hypothesis",
                        "stations": [
                            {"name": "墨脱", "role_hypothesis": "tunnel-system", "confidence": "high"}
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = build_station_outlet_candidates(case_id, tmp_path)

    assert payload is not None
    assert payload["schema_version"] == "station_outlet_candidates.v1"
    assert payload["candidate_status"] == "proxy_candidate_review_ready"
    assert payload["summary"] == {
        "candidate_count": 1,
        "unassigned_case_proxy_anchor_count": 1,
        "eligible_for_delineation_count": 0,
        "role_aligned_candidate_count": 1,
        "manual_validation_priority_count": 1,
        "held_candidate_count": 0,
    }
    candidate = payload["candidates"][0]
    assert candidate["station_id"] == "YJ01"
    assert candidate["candidate_kind"] == "proxy_outlet_candidate"
    assert candidate["eligible_for_delineation"] is False
    assert candidate["system_layout_role_hypothesis"] == "tunnel-system"
    assert candidate["role_alignment_status"] == "aligned_with_role_prior"
    assert candidate["validation_priority"] == "high"
    assert candidate["pre_delineation_review_status"] == "manual_validation_priority"
    assert payload["unassigned_case_proxy_anchors"][0]["label"] == "米林水电站坝址"
