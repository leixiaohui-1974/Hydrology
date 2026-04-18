"""smart_run_reporting 对非阻塞 degraded 的展示语义。"""
from __future__ import annotations

import json

from workflows import smart_run_reporting as target


def test_load_context_keeps_non_blocking_degraded_without_fake_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    contracts_dir = tmp_path / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps(
            {
                "case_id": "demo",
                "profile": "smart",
                "ok": False,
                "has_non_blocking_degraded": True,
                "failure_messages": [],
                "steps": [
                    {
                        "workflow_key": "hyd_cal",
                        "ok": False,
                        "outcome_status": "degraded",
                        "continued": True,
                    },
                    {"workflow_key": "hyd_report", "ok": True, "outcome_status": "completed"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (contracts_dir / "workflow_smart_plan.latest.json").write_text(
        json.dumps({"case_id": "demo", "workflows": [{"workflow_key": "hyd_cal"}, {"workflow_key": "hyd_report"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    profile, plan, results, failures = target.load_smart_run_context_from_contracts("demo")

    assert profile == "smart"
    assert len(plan["workflows"]) == 2
    assert len(results) == 2
    assert failures == []


def test_write_smart_run_index_uses_degraded_overall_status(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    md_path, html_path = target.write_smart_run_index(
        "demo",
        "smart",
        plan={"workflows": [{"workflow_key": "hyd_cal"}, {"workflow_key": "hyd_report"}]},
        results=[
            {
                "workflow_key": "hyd_cal",
                "ok": False,
                "outcome_status": "degraded",
                "continued": True,
                "elapsed_sec": 1.2,
            },
            {
                "workflow_key": "hyd_report",
                "ok": True,
                "outcome_status": "completed",
                "elapsed_sec": 0.8,
            },
        ],
        failures=[],
        report_paths={},
        reporting_cfg={"_config_source": "test"},
        mode="simple",
    )

    md = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")

    assert "整体状态: **完成但有降级步骤**" in md
    assert "| 1 | `hyd_cal` | 降级继续 | 1.2 |" in md
    assert "整体状态: <strong>完成但有降级步骤</strong>" in html
    assert '<td class=degraded>降级继续</td>' in html
