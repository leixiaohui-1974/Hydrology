from __future__ import annotations

import json
from pathlib import Path

from scripts.station_evidence_findings import build_station_evidence_findings


def test_build_station_evidence_findings_from_raw_inputs(tmp_path: Path) -> None:
    case_id = "demo_case"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    raw_dir = tmp_path / "cases" / case_id / "ingest" / "raw"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "station_evidence_search_plan.latest.json").write_text(
        json.dumps({"case_id": case_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    (contracts_dir / "station_pre_delineation_review.latest.json").write_text(
        json.dumps({"case_id": case_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    (raw_dir / "station_evidence_findings.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "station_findings": [
                    {
                        "finding_id": "f1",
                        "station_id": "YJ01",
                        "station_name": "墨脱水电站",
                        "source_attribution": {
                            "source_url": "https://example.com/eia",
                            "publisher_tier": "official",
                        },
                        "claims": [
                            {"claim_type": "coordinate", "claim_value": "29.3,95.3"},
                            {"claim_type": "hydrography_alignment", "claim_value": "mainstem"},
                        ],
                        "promotion_guardrails": {
                            "promotion_blockers": ["missing_second_source"]
                        },
                    }
                ],
                "unassigned_findings": [
                    {
                        "finding_id": "f2",
                        "source_attribution": {
                            "source_url": "https://example.com/news",
                            "publisher_tier": "quasi_official",
                        },
                        "claims": [
                            {"claim_type": "dam_site_text", "claim_value": "米林坝址"}
                        ],
                        "promotion_guardrails": {
                            "promotion_blockers": ["unassigned"]
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = build_station_evidence_findings(case_id, tmp_path)

    assert payload is not None
    assert payload["schema_version"] == "station_evidence_findings.v1"
    assert payload["ingest_status"] == "review_only_findings_ready"
    assert payload["summary"] == {
        "finding_count": 2,
        "station_count_with_findings": 1,
        "coordinate_claim_count": 1,
        "hydrography_claim_count": 1,
        "official_source_count": 1,
        "quasi_official_source_count": 1,
        "blocked_promotion_count": 2,
    }
