import sys
import json
from pathlib import Path

import workflows.build_release_manifest as build_release_manifest
import workflows.build_review_bundle as build_review_bundle


def test_build_review_bundle_defaults_to_case_contract_paths(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    hydrology_root = tmp_path / "Hydrology"
    hydrology_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(build_review_bundle, "BASE_DIR", hydrology_root)
    monkeypatch.setattr(
        build_review_bundle,
        "run_python",
        lambda path, args: calls.append((str(path), list(args))),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_review_bundle.py",
            "--case-id",
            "daduhe",
            "--run-id",
            "run-001",
        ],
    )

    build_review_bundle.main()

    _, args = calls[0]
    contracts_dir = hydrology_root / "cases" / "daduhe" / "contracts"
    assert args[args.index("--report-output") + 1] == str(contracts_dir / "e2e_review_bundle.html")
    assert args[args.index("--review-output") + 1] == str(contracts_dir / "review_bundle.json")


def test_build_release_manifest_defaults_to_case_contract_path(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    hydrology_root = tmp_path / "Hydrology"
    hydrology_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(build_release_manifest, "BASE_DIR", hydrology_root)
    monkeypatch.setattr(
        build_release_manifest,
        "run_python",
        lambda path, args: calls.append((str(path), list(args))),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release_manifest.py",
            "--case-id",
            "daduhe",
            "--version",
            "v1.0.0",
            "--workflow-run",
            "cases/daduhe/contracts/workflow_run.json",
            "--review-bundle",
            "cases/daduhe/contracts/review_bundle.json",
        ],
    )

    build_release_manifest.main()

    _, args = calls[0]
    contracts_dir = hydrology_root / "cases" / "daduhe" / "contracts"
    assert args[args.index("--output") + 1] == str(contracts_dir / "release_manifest.json")


def test_build_review_bundle_adds_report_stack_metadata(monkeypatch, tmp_path: Path) -> None:
    hydrology_root = tmp_path / "Hydrology"
    hydrology_root.mkdir(parents=True, exist_ok=True)
    contracts_dir = hydrology_root / "cases" / "daduhe" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "operations_stage_report.latest.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "final_report.latest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(build_review_bundle, "BASE_DIR", hydrology_root)

    def fake_run_python(path, args):
        review_output = Path(args[args.index("--review-output") + 1])
        review_output.parent.mkdir(parents=True, exist_ok=True)
        review_output.write_text(
            json.dumps(
                {
                    "review_id": "review-001",
                    "run_id": "run-001",
                    "case_id": "daduhe",
                    "verdict": "pass_with_comments",
                    "findings": [],
                    "report_artifacts": [],
                    "metadata": {},
                    "schema_version": "0.1.0",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(build_review_bundle, "run_python", fake_run_python)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_review_bundle.py",
            "--case-id",
            "daduhe",
            "--run-id",
            "run-001",
        ],
    )

    build_review_bundle.main()

    payload = json.loads((contracts_dir / "review_bundle.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["report_stack"]["summary"]["stage_report_count"] == 1
    assert payload["metadata"]["report_stack"]["summary"]["final_report_count"] == 1


def test_build_release_manifest_adds_report_stack_metadata_and_artifacts(monkeypatch, tmp_path: Path) -> None:
    hydrology_root = tmp_path / "Hydrology"
    hydrology_root.mkdir(parents=True, exist_ok=True)
    contracts_dir = hydrology_root / "cases" / "daduhe" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "operations_stage_report.latest.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "model_report.latest.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "autonomy_assess__autonomy_assess__default_algorithm_report.latest.json").write_text("{}", encoding="utf-8")
    (contracts_dir / "final_report.latest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(build_release_manifest, "BASE_DIR", hydrology_root)

    def fake_run_python(path, args):
        output = Path(args[args.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "release_id": "release-001",
                    "case_id": "daduhe",
                    "version": "v1.0.0",
                    "channel": "staging",
                    "status": "published",
                    "included_runs": ["run-001"],
                    "review_refs": ["review-001"],
                    "artifacts": [],
                    "metadata": {},
                    "schema_version": "0.1.0",
                    "governance_gates": {
                        "index_rel": "Hydrology/configs/platform_governance_gates.index.json",
                        "index_version": 1,
                        "note": "test",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(build_release_manifest, "run_python", fake_run_python)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_release_manifest.py",
            "--case-id",
            "daduhe",
            "--version",
            "v1.0.0",
            "--workflow-run",
            "cases/daduhe/contracts/workflow_run.json",
            "--review-bundle",
            "cases/daduhe/contracts/review_bundle.json",
        ],
    )

    build_release_manifest.main()

    payload = json.loads((contracts_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["report_stack"]["summary"]["algorithm_report_count"] == 1
    artifact_paths = {item["path"] for item in payload["artifacts"]}
    assert "cases/daduhe/contracts/operations_stage_report.latest.json" in artifact_paths
    assert "cases/daduhe/contracts/model_report.latest.json" in artifact_paths
    assert "cases/daduhe/contracts/autonomy_assess__autonomy_assess__default_algorithm_report.latest.json" in artifact_paths
    assert "cases/daduhe/contracts/final_report.latest.json" in artifact_paths
