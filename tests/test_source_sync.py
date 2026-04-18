from __future__ import annotations

import json
from pathlib import Path

from workflows.run_source_sync import run_source_sync, run_wxq_sync


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_case(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    raw_root = tmp_path / "wxq-1d" / "demo"
    _write(raw_root / "model_demo.json", "{}")
    _write(raw_root / "demo.sqlite3", "sqlite")
    _write(raw_root / "资料说明.pdf", "pdf")

    case_dir = tmp_path / "cases" / "demo"
    _write(case_dir / "manifest.yaml", "locations:\n  raw_root: wxq-1d/demo\n")

    sidecar = tmp_path / ".graphify" / "pilots" / "case-demo" / "graphify-out"
    _write(sidecar / "GRAPH_REPORT.md", "## Summary\n- demo graph\n")
    _write(sidecar / "run_summary.json", json.dumps({"mode": "structural", "file_count": 3}))

    monkeypatch.setattr(
        "workflows.run_source_sync.WORKSPACE",
        tmp_path,
    )
    monkeypatch.setattr(
        "workflows.run_source_sync.WIKI_DIR",
        tmp_path / "wiki",
    )
    monkeypatch.setattr(
        "workflows.run_source_sync.load_case_config",
        lambda *a, **k: {
            "scan_dirs": ["wxq-1d/demo"],
            "topology_json_paths": ["wxq-1d/demo/model_demo.json"],
            "sqlite_paths": ["wxq-1d/demo/demo.sqlite3"],
            "dem_path": "",
            "river_network_path": "",
            "source_bundle_path": "",
        },
    )
    monkeypatch.setattr(
        "workflows.run_source_sync.load_case_manifest",
        lambda *a, **k: (case_dir / "manifest.yaml", {"locations": {"raw_root": "wxq-1d/demo"}}),
    )
    monkeypatch.setattr(
        "workflows.run_source_sync.default_graphify_case_sidecar_dir",
        lambda case_id: sidecar,
    )
    return case_dir, sidecar


def test_run_source_sync_writes_contracts_and_wiki(monkeypatch, tmp_path: Path) -> None:
    case_dir, _ = _prepare_case(tmp_path, monkeypatch)

    result = run_source_sync("demo")

    registry = json.loads((case_dir / "contracts" / "source_registry.latest.json").read_text(encoding="utf-8"))
    summary = json.loads((case_dir / "contracts" / "source_summary.latest.json").read_text(encoding="utf-8"))
    data_resources = (tmp_path / "wiki" / "data-resources.md").read_text(encoding="utf-8")
    cases_deep_dive = (tmp_path / "wiki" / "cases-deep-dive.md").read_text(encoding="utf-8")
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")

    assert result["case_id"] == "demo"
    assert registry["summary"]["total_files"] == 3
    assert summary["graphify_sidecar"]["status"] == "present"
    assert "source_summary.latest.json" in data_resources
    assert "Source Sync" in cases_deep_dive
    assert "source-sync" in log
    assert (case_dir / "contracts" / "wxq_source_registry.latest.json").exists()
    assert (case_dir / "contracts" / "wxq_source_summary.latest.json").exists()


def test_run_source_sync_can_skip_wiki(monkeypatch, tmp_path: Path) -> None:
    case_dir, _ = _prepare_case(tmp_path, monkeypatch)

    result = run_source_sync("demo", skip_wiki_sync=True)

    assert result["wiki_sync"]["enabled"] is False
    assert (case_dir / "contracts" / "source_registry.latest.json").exists()
    assert not (tmp_path / "wiki" / "data-resources.md").exists()


def test_run_wxq_sync_alias_still_works(monkeypatch, tmp_path: Path) -> None:
    case_dir, _ = _prepare_case(tmp_path, monkeypatch)

    result = run_wxq_sync("demo", skip_wiki_sync=True)

    assert result["case_id"] == "demo"
    assert (case_dir / "contracts" / "source_summary.latest.json").exists()
    assert (case_dir / "contracts" / "wxq_source_summary.latest.json").exists()
