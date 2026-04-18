from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.run_deep_asset_recorder import record_assets
from workflows.run_knowledge_registry import build_registry


def _prepare_sidecar(tmp_path: Path) -> Path:
    sidecar = tmp_path / "graphify"
    sidecar.mkdir()
    (sidecar / "GRAPH_REPORT.md").write_text("# Graph Report\n", encoding="utf-8")
    (sidecar / "concept_candidates.json").write_text(
        json.dumps([{"id": "c1"}]), encoding="utf-8"
    )
    return sidecar


def test_record_assets_reports_graphify_sidecar(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("workflows.run_deep_asset_recorder.load_case_config", lambda *a, **k: {"scan_dirs": []})
    sidecar = _prepare_sidecar(tmp_path)
    report = record_assets("demo_case", dry_run=True, graphify_sidecar_dir=str(sidecar))
    assert report["graphify_sidecar"]["status"] == "present"
    assert report["graphify_sidecar"]["concept_candidate_count"] == 1


def test_build_registry_reports_graphify_sidecar(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("workflows.run_knowledge_registry.scan_assets", lambda *a, **k: {"assets": {}, "scripts": {}})
    monkeypatch.setattr("workflows.run_knowledge_registry.extract_best_metrics", lambda *a, **k: {})
    monkeypatch.setattr("workflows.run_knowledge_registry.load_registry", lambda *a, **k: {})
    monkeypatch.setattr("workflows.run_knowledge_registry.save_registry", lambda *a, **k: None)
    monkeypatch.setattr("workflows.run_knowledge_registry._find_unintegrated", lambda *a, **k: [])
    sidecar = _prepare_sidecar(tmp_path)
    registry = build_registry("demo_case", graphify_sidecar_dir=str(sidecar))
    assert registry["graphify_sidecar"]["status"] == "present"
    assert registry["graphify_sidecar"]["concept_candidate_count"] == 1


def test_scan_assets_tolerates_broken_symlink_file(monkeypatch, tmp_path: Path) -> None:
    case_id = "demo_case"
    case_dir = tmp_path / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    broken = case_dir / "manifest.yaml"
    broken.symlink_to(broken)
    monkeypatch.setattr("workflows.run_knowledge_registry.WORKSPACE", tmp_path)
    monkeypatch.setattr("workflows.run_knowledge_registry.load_case_config", lambda *a, **k: {"scan_dirs": []})

    result = build_registry.__globals__["scan_assets"](case_id)
    rel = f"cases/{case_id}/manifest.yaml"
    assert rel in result["assets"]
    assert result["assets"][rel]["broken_link"] is True
