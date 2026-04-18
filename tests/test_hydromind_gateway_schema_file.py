"""hydromind_gateway.v1 JSON Schema 文件存在且带版本（战役 Phase 4）。"""

from __future__ import annotations

import json
from pathlib import Path


def test_hydromind_gateway_schema_versioned() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/architecture/agent-system/schemas/hydromind_gateway.v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("version") == "1.1.0"
    assert "$defs" in data
    defs = data["$defs"]
    for key in (
        "ping_request",
        "ping_response",
        "list_tools_request",
        "list_tools_response",
        "invoke_tool_request",
        "invoke_tool_response",
        "gateway_error_envelope",
    ):
        assert key in defs
    assert "policy" in json.dumps(defs["list_tools_response"])
