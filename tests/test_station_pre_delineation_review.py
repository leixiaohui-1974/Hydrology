from __future__ import annotations

import json
from pathlib import Path

from scripts.station_pre_delineation_review import build_station_pre_delineation_review


def test_build_station_pre_delineation_review_from_outlet_candidates(tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "station_outlet_candidates.latest.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "candidates": [
                    {
                        "candidate_id": "demo-candidate-01",
                        "station_id": "YJ01",
                        "station_name": "墨脱水电站",
                        "pre_delineation_review_status": "manual_validation_priority",
                        "validation_priority": "high",
                        "system_layout_role_hypothesis": "tunnel-system",
                        "role_alignment_status": "aligned_with_role_prior",
                        "lat": 29.3,
                        "lon": 95.3,
                        "display_name": "墨脱县, 墨脱镇, 中国",
                        "source_type": "city",
                        "source_category": "place",
                        "authoritative": False,
                        "eligible_for_delineation": False,
                        "limitations": ["proxy_only_not_authoritative_outlet"],
                        "recommended_next_step": "优先补证据。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = build_station_pre_delineation_review(case_id, tmp_path)

    assert payload is not None
    assert payload["schema_version"] == "station_pre_delineation_review.v1"
    assert payload["review_status"] == "manual_validation_priority"
    assert payload["summary"] == {
        "review_candidate_count": 1,
        "manual_validation_priority_count": 1,
        "hold_count": 0,
        "needs_corroboration_count": 1,
        "ready_for_manual_geo_review_count": 0,
        "partially_resolved_count": 0,
        "unresolved_count": 1,
    }
    row = payload["review_candidates"][0]
    assert row["station_name"] == "墨脱水电站"
    assert row["review_status"] == "manual_validation_priority"
    assert row["evidence_gaps"] == [
        "needs_hydrography_alignment",
        "needs_dam_or_powerhouse_coordinate",
        "current_candidate_is_place_proxy_not_engineering_asset",
    ]
    assert row["review_checklist"] == [
        "核对候选点是否位于目标河段/支流附近",
        "补充坝址、厂房或控制断面的更强坐标证据",
        "补充水系或主河道吸附证据，验证候选点与河网关系",
    ]
    assert row["independent_evidence_families"] == [
        "proxy_geocode_candidate",
        "system_layout_role_prior",
    ]
    assert row["independent_evidence_family_count"] == 2
    assert row["required_evidence"] == [
        "hydrography",
        "dam_site_coordinate",
        "second_independent_geo_source",
    ]
    assert row["promotion_blockers"] == [
        "needs_hydrography_alignment",
        "needs_dam_or_powerhouse_coordinate",
        "current_candidate_is_place_proxy_not_engineering_asset",
        "second_independent_geo_source",
        "candidate_is_not_authoritative",
        "candidate_not_eligible_for_delineation",
    ]
    assert row["blocker_accounting"] == {
        "matched_finding_count": 0,
        "resolved_blockers": [],
        "remaining_blockers": [
            "needs_hydrography_alignment",
            "needs_dam_or_powerhouse_coordinate",
            "current_candidate_is_place_proxy_not_engineering_asset",
            "second_independent_geo_source",
            "candidate_is_not_authoritative",
            "candidate_not_eligible_for_delineation",
        ],
        "resolution_status": "unresolved",
    }
    assert row["evidence_gate_status"] == "needs_corroboration"
    assert row["recommended_public_source_types"][0]["source_type"] == "环评公示稿/环评批复"
    assert row["recommended_query_patterns"][:3] == [
        "墨脱水电站 坐标",
        "墨脱水电站 坝址",
        "墨脱水电站 地理坐标",
    ]
    assert row["recommended_next_step"] == "优先补证据。"
