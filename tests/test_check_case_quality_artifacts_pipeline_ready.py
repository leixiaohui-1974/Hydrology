from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import check_case_quality_artifacts as target


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pipeline_contract_ready_uses_outcome_fallback_for_canal_cases(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        case_id = "demo_case"
        contracts_dir = workspace / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        outcomes_dir.mkdir(parents=True, exist_ok=True)

        config_path = workspace / "Hydrology" / "configs" / "loop.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(
                {
                    "quality_loop": {
                        "dimensions": [
                            {"key": "demo", "display_zh": "demo", "artifact_hints": ["workflow_run.json"]},
                        ]
                    }
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        _write_json(
            contracts_dir / "workflow_run.json",
            {"outputs": [{"path": "cases/demo_case/contracts/outcomes/model.latest.json"}]},
        )
        _write_json(
            contracts_dir / "data_pack.latest.json",
            {
                "source_bundle_json": "cases/demo_case/contracts/source_bundle.contract.json",
                "review_gates": {
                    "basin_validation_json": "external/basin_validation.json",
                },
            },
        )
        _write_json(contracts_dir / "source_bundle.contract.json", {"records": []})
        _write_json(outcomes_dir / "source_to_delineation.latest.json", {"ok": True})
        _write_json(outcomes_dir / "model.latest.json", {"ok": True})
        _write_json(workspace / "external" / "basin_validation.json", {"ok": True})

        monkeypatch.setattr(target, "WORKSPACE", workspace)

        result = target.run_check(case_id, config_path)
        summary = result["summary"]
        assert summary["data_pack_basin_validation_present"] is True
        assert summary["delineation_present"] is True
        assert summary["hydrology_sim_present"] is True
        assert summary["pipeline_contract_ready"] is True


def test_pipeline_contract_ready_uses_dem_validation_for_daduhe_style_case(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        case_id = "demo_case"
        contracts_dir = workspace / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        outcomes_dir.mkdir(parents=True, exist_ok=True)

        config_path = workspace / "Hydrology" / "configs" / "loop.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(
                {
                    "quality_loop": {
                        "dimensions": [
                            {"key": "demo", "display_zh": "demo", "artifact_hints": ["workflow_run.json"]},
                        ]
                    }
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        _write_json(
            contracts_dir / "workflow_run.json",
            {"outputs": [{"path": "cases/demo_case/contracts/hydrology_sim.latest.json"}]},
        )
        _write_json(
            contracts_dir / "data_pack.latest.json",
            {
                "source_bundle_json": "cases/demo_case/contracts/source_bundle.contract.json",
                "summary": {
                    "dem_outlet_validation": {
                        "all_outlets_within_dem": True,
                    }
                },
            },
        )
        _write_json(contracts_dir / "source_bundle.contract.json", {"records": []})
        _write_json(contracts_dir / "delineation.latest.json", {"ok": True})
        _write_json(contracts_dir / "hydrology_sim.latest.json", {"ok": True})

        monkeypatch.setattr(target, "WORKSPACE", workspace)

        result = target.run_check(case_id, config_path)
        summary = result["summary"]
        assert summary["data_pack_basin_validation_present"] is True
        assert summary["pipeline_contract_ready"] is True
