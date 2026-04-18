import sys
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
    contracts_dir = hydrology_root.parent / "cases" / "daduhe" / "contracts"
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
    contracts_dir = hydrology_root.parent / "cases" / "daduhe" / "contracts"
    assert args[args.index("--output") + 1] == str(contracts_dir / "release_manifest.json")
