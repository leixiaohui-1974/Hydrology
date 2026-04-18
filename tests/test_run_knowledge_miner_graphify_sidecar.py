from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.run_knowledge_miner import _load_graphify_sidecar


def test_load_graphify_sidecar_reports_present_artifacts(tmp_path: Path) -> None:
    sidecar = tmp_path / "graphify"
    sidecar.mkdir()
    (sidecar / "GRAPH_REPORT.md").write_text(
        "# Graph Report - demo\n\n## Summary\n- 10 nodes · 20 edges\n\n## God Nodes (most connected - your core abstractions)\n1. `ConfigParser` - 7 edges\n\n## Surprising Connections (you probably didn't know these)\n- `A` --uses--> `B`\n",
        encoding="utf-8",
    )
    (sidecar / "run_summary.json").write_text(
        json.dumps({"mode": "structural", "file_count": 12, "node_count": 10, "edge_count": 20}),
        encoding="utf-8",
    )
    (sidecar / "db_sidecar_run_summary.json").write_text(
        json.dumps({"sqlite_count": 2, "dump_count": 5, "output_dir": "cases/demo/graphify/db_sidecar"}),
        encoding="utf-8",
    )
    (sidecar / "concept_candidates.json").write_text(
        json.dumps(
            [
                {"id": "c1", "type": "topology_node", "tags": ["node", "reservoir"]},
                {"id": "c2", "category": "boundary_condition", "summary": "rainfall inflow boundary"},
            ]
        ),
        encoding="utf-8",
    )
    (sidecar / "relation_candidates.json").write_text(
        json.dumps([{"id": "r1", "relation": "control schedule edge"}]), encoding="utf-8"
    )

    payload = _load_graphify_sidecar(str(sidecar))

    assert payload["status"] == "present"
    assert payload["concept_candidate_count"] == 2
    assert payload["relation_candidate_count"] == 1
    assert payload["supports_auto_modeling_hints"] is True
    assert payload["modeling_signal_counts"]["topology"] >= 1
    assert payload["modeling_signal_counts"]["boundary"] >= 1
    assert payload["modeling_signal_counts"]["control"] >= 1
    assert payload["graph_run_summary"]["node_count"] == 10
    assert payload["db_sidecar_summary"]["sqlite_count"] == 2
    assert payload["graph_report_summary"]["summary_bullets"][0] == "10 nodes · 20 edges"
    assert "ConfigParser" in payload["graph_report_summary"]["god_nodes"][0]
    kinds = {item["kind"] for item in payload["artifacts"]}
    assert "graph_report" in kinds
    assert "run_summary" in kinds
    assert "db_sidecar_run_summary" in kinds
    assert "concept_candidates" in kinds
    assert "relation_candidates" in kinds


def test_load_graphify_sidecar_missing_dir_is_nonfatal(tmp_path: Path) -> None:
    payload = _load_graphify_sidecar(str(tmp_path / "missing-sidecar"))
    assert payload["status"] == "missing"
