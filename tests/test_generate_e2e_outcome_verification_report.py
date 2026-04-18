from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import workflows.generate_e2e_outcome_verification_report as target


def test_resolve_source_report_path_falls_back_from_hydrology_prefixed_cases_path(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path
    report_path = workspace / "cases" / "demo" / "contracts" / "source_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('{"agent_results":[]}', encoding="utf-8")

    monkeypatch.setattr(target, "WORKSPACE", workspace)
    progress = {"source_report": "Hydrology/cases/demo/contracts/source_report.json"}

    resolved = target._resolve_source_report_path(progress)
    assert resolved == report_path


def test_build_outcome_coverage_report_ignores_retired_non_registry_workflows(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path
    contracts_dir = workspace / "cases" / "demo" / "contracts" / "outcomes"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(target, "WORKSPACE", workspace)

    for key in ["deep_record", "data_audit", "hil_acceptance_test_ext"]:
        (contracts_dir / f"{key}.latest.json").write_text(
            json.dumps(
                {
                    "template_id": "generic_template",
                    "contract_path": f"cases/demo/contracts/outcomes/{key}.latest.json",
                    "dimensions": {
                        "conclusion": [{"evidence_path": "cases/demo/contracts/some.json"}],
                        "recommendation": [{"evidence_path": "cases/demo/contracts/some.json"}],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    progress = {
        "case_id": "demo",
        "last_updated_at": "2026-04-13T00:00:00Z",
        "records": [
            {"workflow_key": "deep_record", "status": "passed"},
            {"workflow_key": "data_audit", "status": "passed"},
            {"workflow_key": "hil_acceptance_test_ext", "status": "passed"},
            {"workflow_key": "daduhe_full_pipeline_ext", "status": "failed"},
            {"workflow_key": "daduhe_real_validation_ext", "status": "failed"},
        ],
    }

    report = target._build_outcome_coverage_report(progress)
    assert report["total_executed"] == 3
    assert report["outcomes_generated"] == 3
    assert report["gate_status"] == "passed"
    assert "daduhe_full_pipeline_ext" not in report["missing_workflows"]
    assert "daduhe_real_validation_ext" not in report["invalid_workflows"]
