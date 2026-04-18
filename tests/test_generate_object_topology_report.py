from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.generate_object_topology_report import generate_object_topology_report


def test_generate_object_topology_report_exports_standard_object_samples(tmp_path: Path) -> None:
    output_path = tmp_path / "combined_object_topology_report.md"

    result = generate_object_topology_report(
        case_id="daduhe",
        contracts_dir=tmp_path,
        output_path=output_path,
    )

    assert output_path.exists()
    assert result["object_report_index"].exists()
    assert result["object_report_summary"].exists()

    index_payload = json.loads(result["object_report_index"].read_text(encoding="utf-8"))
    report_items = {item["object_type"]: item for item in index_payload["reports"]}

    assert report_items["Reservoir"]["status"] == "available"
    assert report_items["Gate"]["status"] == "missing"

    markdown = output_path.read_text(encoding="utf-8")
    assert "标准对象报告样本" in markdown
    assert "PumpStation" in markdown
