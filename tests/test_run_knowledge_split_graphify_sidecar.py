from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.run_knowledge_split import split_knowledge


def test_split_knowledge_reports_graphify_sidecar(tmp_path: Path) -> None:
    yaml_path = tmp_path / "demo_case.yaml"
    yaml_path.write_text(
        "case_id: demo_case\nknowledge:\n  discovered_assets: {}\n",
        encoding="utf-8",
    )

    sidecar = tmp_path / "graphify"
    sidecar.mkdir()
    (sidecar / "concept_candidates.json").write_text(json.dumps([{"id": "c1"}]), encoding="utf-8")

    result = split_knowledge(
        "demo_case",
        config_path=str(yaml_path),
        dry_run=True,
        graphify_sidecar_dir=str(sidecar),
    )

    assert result["graphify_sidecar"]["status"] == "present"
    assert result["graphify_sidecar"]["concept_candidate_count"] == 1
