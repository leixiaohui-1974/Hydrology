from __future__ import annotations

import json
from pathlib import Path

from scripts.station_proxy_outlet_anchors import build_station_proxy_outlet_anchors


def test_build_station_proxy_outlet_anchors_from_review_candidates(tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "station_geocode_candidates.latest.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "review_anchor_candidates": [
                    {
                        "owner_kind": "hint",
                        "owner_id": "milin_hint",
                        "label": "米林水电站坝址",
                        "query": "米林镇",
                        "candidate": {
                            "name": "米林镇",
                            "display_name": "米林镇, 米林市, 林芝市, 西藏自治区, 中国",
                            "lat": 29.2196768,
                            "lon": 94.2141579,
                            "category": "boundary",
                            "type": "administrative",
                            "anchor_score": 4.2,
                            "anchor_signals": {"proxy_class": "admin_area_proxy"},
                        },
                    },
                    {
                        "owner_kind": "hint",
                        "owner_id": "yusong_hint",
                        "label": "玉松",
                        "query": "玉松",
                        "candidate": {
                            "name": "玉松村",
                            "display_name": "玉松村, 米林市, 林芝市, 西藏自治区, 中国",
                            "lat": 29.1951649,
                            "lon": 94.0508896,
                            "category": "place",
                            "type": "village",
                            "anchor_score": 3.44,
                            "anchor_signals": {"proxy_class": "locality_proxy"},
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = build_station_proxy_outlet_anchors(case_id, tmp_path)

    assert payload is not None
    assert payload["schema_version"] == "station_proxy_outlet_anchors.v1"
    assert payload["anchor_status"] == "proxy_review_ready"
    assert payload["summary"] == {
        "anchor_count": 2,
        "station_proxy_anchor_count": 0,
        "unassigned_case_proxy_anchor_count": 2,
        "rejected_candidate_count": 0,
        "owner_count": 2,
        "admin_area_anchor_count": 1,
        "locality_anchor_count": 1,
    }
    assert payload["station_proxy_anchors"] == []
    assert payload["unassigned_case_proxy_anchors"][0]["anchor_kind"] == "proxy_admin_area"
    assert payload["unassigned_case_proxy_anchors"][0]["confidence"] == "medium"
    assert payload["unassigned_case_proxy_anchors"][1]["anchor_kind"] == "proxy_locality"
    assert payload["unassigned_case_proxy_anchors"][1]["confidence"] == "low"
