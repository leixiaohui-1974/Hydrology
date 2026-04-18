#!/usr/bin/env python3
"""将 workflows.WORKFLOW_REGISTRY 导出为 HydroDesk Playwright / VITE_PLAYWRIGHT 注入用 JSON。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HYDRODESK_FIXTURE = _REPO_ROOT / "HydroDesk" / "src" / "config" / "workflowRegistry.playwright.fixture.json"


def main() -> int:
    sys.path.insert(0, str(_REPO_ROOT / "Hydrology"))
    from workflows import list_workflows  # noqa: PLC0415

    out = [
        {
            "name": item["name"],
            "description": str(item.get("description", "")),
            "required_args": list(item.get("args", [])),
        }
        for item in sorted(list_workflows(), key=lambda x: x["name"])
    ]
    _HYDRODESK_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _HYDRODESK_FIXTURE.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(out)} workflows -> {_HYDRODESK_FIXTURE.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
