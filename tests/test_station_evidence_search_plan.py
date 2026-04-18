from __future__ import annotations

import json
from pathlib import Path

from scripts.station_evidence_search_plan import build_station_evidence_search_plan


def test_build_station_evidence_search_plan_from_pre_delineation_review(tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "station_pre_delineation_review.latest.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "review_candidates": [
                    {
                        "candidate_id": "demo-candidate-01",
                        "station_id": "YJ01",
                        "station_name": "墨脱水电站",
                        "review_status": "manual_validation_priority",
                        "validation_priority": "high",
                        "evidence_gate_status": "needs_corroboration",
                        "required_evidence": ["hydrography", "dam_site_coordinate"],
                        "recommended_public_source_types": [
                            {"source_type": "环评公示稿/环评批复", "why": "坐标级证据优先"}
                        ],
                        "recommended_query_patterns": ["墨脱水电站 坐标", "墨脱四级水电站"],
                        "recommended_next_step": "优先补证据。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = build_station_evidence_search_plan(case_id, tmp_path)

    assert payload is not None
    assert payload["schema_version"] == "station_evidence_search_plan.v1"
    assert payload["plan_status"] == "ready_to_search"
    assert payload["summary"] == {
        "plan_count": 1,
        "manual_validation_priority_count": 1,
        "needs_corroboration_count": 1,
    }
    plan = payload["plans"][0]
    assert plan["station_name"] == "墨脱水电站"
    assert plan["search_goal"] == "collect_coordinate_grade_or_hydrography_adjacent_evidence"
    assert plan["recommended_query_patterns"] == ["墨脱水电站 坐标", "墨脱四级水电站"]
