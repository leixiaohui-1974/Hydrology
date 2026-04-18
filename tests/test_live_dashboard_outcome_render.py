"""Dashboard should render from outcome contracts."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.run_e2e_live_tracker import (
    _business_navigation_assets,
    _outcome_cards,
    _render_dashboard,
    _render_dashboard_html,
)


class TestLiveDashboardOutcomeRender(unittest.TestCase):
    def test_dashboard_summary_prefers_coverage_report_values(self) -> None:
        case_id = "ut_outcome_summary_sync"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        md_path = contracts_dir / "E2E_LIVE_DASHBOARD.md"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        (contracts_dir / "outcome_coverage_report.latest.json").write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "generated_at": "2026-04-02T00:00:00+00:00",
                    "threshold": 0.95,
                    "total_executed": 1,
                    "outcomes_generated": 1,
                    "schema_valid_count": 1,
                    "evidence_bound_count": 1,
                    "outcome_coverage": 1.0,
                    "gate_status": "passed",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        state = {
            "run_id": "live-ut-sync",
            "case_id": case_id,
            "started_at": "2026-04-02T00:00:00+00:00",
            "last_updated_at": "2026-04-02T00:00:01+00:00",
            "execution_profile": "fast_validation",
            "retry": {"max_retries": 1},
            "source_report": str(contracts_dir / "source_report.json"),
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "timeout": 0,
                "pending": 0,
                "retries_used": 0,
                "outcomes_generated": 0,
                "outcome_coverage": 0.0,
                "outcome_gate_status": "blocked",
                "outcome_gate_threshold": 0.95,
                "outcome_coverage_report": f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
            },
            "current": None,
            "records": [],
        }
        (contracts_dir / "source_report.json").write_text('{"agent_results":[]}', encoding="utf-8")
        try:
            _render_dashboard(md_path, state)
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("outcomes_generated: **1**", content)
            self.assertIn("outcome_coverage: **100.0%**", content)
            self.assertIn("outcome_gate_status: **passed**", content)
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)

    def test_dashboard_uses_outcome_contract_and_new_section_name(self) -> None:
        case_id = "ut_outcome_dashboard"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        md_path = contracts_dir / "E2E_LIVE_DASHBOARD.md"
        outcomes_dir.mkdir(parents=True, exist_ok=True)

        outcome = {
            "schema_version": "1.0.0",
            "contract_type": "workflow_outcome",
            "workflow_key": "data_audit",
            "case_id": case_id,
            "template_id": "data_audit_template",
            "category": "data_quality",
            "status": "completed",
            "generated_at": "2026-04-02T00:00:00+00:00",
            "dimensions": {
                "data": [],
                "business": [],
                "process": [{"label": "执行摘要", "value": "数据审计已完成"}],
                "method": [],
                "result": [],
                "accuracy": [],
                "conclusion": [{"label": "结论", "value": "数据质量可用"}],
                "recommendation": [{"label": "建议", "value": "建议继续跑精度评估"}],
            },
            "artifacts": [{"path": f"cases/{case_id}/contracts/data_quality_audit.latest.json", "exists": True}],
            "slots": {
                "topology": [],
                "gis": [],
                "charts": [],
                "tables": [],
                "conclusions": [],
                "recommendations": [],
            },
            "metrics": {"nse": 0.91},
        }
        (outcomes_dir / "data_audit.latest.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        state = {
            "run_id": "live-ut",
            "case_id": case_id,
            "started_at": "2026-04-02T00:00:00+00:00",
            "last_updated_at": "2026-04-02T00:00:01+00:00",
            "execution_profile": "fast_validation",
            "retry": {"max_retries": 1},
            "source_report": str(contracts_dir / "source_report.json"),
            "summary": {"total": 1, "passed": 1, "failed": 0, "timeout": 0, "pending": 0, "retries_used": 0},
            "current": None,
            "records": [
                {
                    "agent_id": "tanyuan",
                    "agent_name": "探源",
                    "workflow_key": "data_audit",
                    "status": "passed",
                    "started_at": "2026-04-02T00:00:00+00:00",
                    "ended_at": "2026-04-02T00:00:01+00:00",
                    "duration_s": 1.0,
                    "attempts": 1,
                    "excerpt": "{}",
                }
            ],
        }
        (contracts_dir / "source_report.json").write_text(
            json.dumps(
                {
                    "agent_results": [
                        {
                            "agent_id": "tanyuan",
                            "agent_name": "探源",
                            "workflow_results": [{"workflow_key": "data_audit"}],
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            _render_dashboard(md_path, state)
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("业务成果导航区（模板化六件套）", content)
            self.assertIn("模板成果卡片（结果资产优先）", content)
            self.assertIn("Agent 职责与承接工作", content)
            self.assertIn("数据勘探与知识发现", content)
            self.assertIn("数据审计已完成", content)
            self.assertIn("nse=0.91", content)
            self.assertIn("数据质量可用 / 建议继续跑精度评估", content)
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)

    def test_outcome_cards_use_effective_status_instead_of_raw_record_status(self) -> None:
        case_id = "ut_outcome_card_status"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        outcomes_dir.mkdir(parents=True, exist_ok=True)
        (outcomes_dir / "strict_revalidation_ext.latest.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "contract_type": "workflow_outcome",
                    "workflow_key": "strict_revalidation_ext",
                    "case_id": case_id,
                    "template_id": "control_scheduling_template",
                    "category": "control",
                    "status": "quality_failed",
                    "dimensions": {
                        "data": [],
                        "business": [],
                        "process": [{"label": "执行状态", "value": "quality_failed"}],
                        "method": [],
                        "result": [],
                        "accuracy": [],
                        "conclusion": [{"label": "结论", "value": "严格复核共发现 3 个失败项。"}],
                        "recommendation": [],
                    },
                    "artifacts": [],
                    "slots": {
                        "topology": [],
                        "gis": [],
                        "charts": [],
                        "tables": [],
                        "conclusions": [],
                        "recommendations": [],
                    },
                    "metrics": {"failed_tests": 3},
                    "contract_path": f"cases/{case_id}/contracts/outcomes/strict_revalidation_ext.latest.json",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        state = {
            "case_id": case_id,
            "records": [
                {
                    "workflow_key": "strict_revalidation_ext",
                    "agent_name": "闭环",
                    "status": "passed",
                }
            ],
        }
        try:
            cards = _outcome_cards(state)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["status"], "failed")
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)

    def test_navigation_prefers_case_results_over_raw_sources(self) -> None:
        case_id = "ut_outcome_nav"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        outcomes_dir.mkdir(parents=True, exist_ok=True)
        (contracts_dir / "section_analysis.latest.json").write_text("{}", encoding="utf-8")

        outcome = {
            "schema_version": "1.0.0",
            "contract_type": "workflow_outcome",
            "workflow_key": "section_analysis",
            "case_id": case_id,
            "template_id": "modeling_simulation_template",
            "category": "simulation",
            "status": "completed",
            "generated_at": "2026-04-02T00:00:00+00:00",
            "dimensions": {
                "data": [],
                "business": [],
                "process": [{"label": "执行摘要", "value": "断面分析已完成"}],
                "method": [],
                "result": [{"label": "核心结果", "value": "已产出结构化断面分析结果"}],
                "accuracy": [{"label": "精度指标", "value": {"overall_score": 0.88}}],
                "conclusion": [{"label": "结论", "value": "断面质量可用"}],
                "recommendation": [{"label": "建议", "value": "建议进入耦合仿真"}],
            },
            "artifacts": [
                {"path": "wxq-1d/大渡河/raw/section.xlsx", "exists": True},
            ],
            "slots": {
                "topology": [],
                "gis": [],
                "charts": [],
                "tables": [{"path": "wxq-1d/大渡河/raw/section.xlsx", "exists": True}],
                "conclusions": [],
                "recommendations": [],
            },
            "metrics": {"overall_score": 0.88},
        }
        (outcomes_dir / "section_analysis.latest.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        state = {
            "case_id": case_id,
            "records": [
                {
                    "agent_name": "识地",
                    "workflow_key": "section_analysis",
                    "status": "passed",
                }
            ],
        }
        try:
            assets = _business_navigation_assets(state)
            self.assertIn(f"cases/{case_id}/contracts/section_analysis.latest.json", assets["conclusion"])
            self.assertNotIn("wxq-1d/大渡河/raw/section.xlsx", assets["table"])
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)

    def test_html_renders_agent_workflow_inspector_structure(self) -> None:
        case_id = "ut_outcome_html"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        outcomes_dir = contracts_dir / "outcomes"
        html_path = contracts_dir / "E2E_LIVE_DASHBOARD.html"
        outcomes_dir.mkdir(parents=True, exist_ok=True)

        outcome = {
            "schema_version": "1.0.0",
            "contract_type": "workflow_outcome",
            "workflow_key": "data_audit",
            "case_id": case_id,
            "template_id": "data_audit_template",
            "category": "data_quality",
            "status": "completed",
            "generated_at": "2026-04-02T00:00:00+00:00",
            "contract_path": f"cases/{case_id}/contracts/outcomes/data_audit.latest.json",
            "dimensions": {
                "data": [],
                "business": [],
                "process": [{"label": "执行摘要", "value": "数据审计已完成"}],
                "method": [],
                "result": [],
                "accuracy": [{"label": "精度指标", "value": {"nse": 0.91}}],
                "conclusion": [{"label": "结论", "value": "数据质量可用", "evidence_path": f"cases/{case_id}/contracts/data_quality_audit.latest.json"}],
                "recommendation": [{"label": "建议", "value": "建议继续跑精度评估", "evidence_path": f"cases/{case_id}/contracts/data_quality_audit.latest.json"}],
            },
            "artifacts": [{"path": f"cases/{case_id}/contracts/data_quality_audit.latest.json", "exists": True}],
            "slots": {
                "topology": [],
                "gis": [],
                "charts": [],
                "tables": [],
                "conclusions": [{"path": f"cases/{case_id}/contracts/data_quality_audit.latest.json", "exists": True}],
                "recommendations": [],
            },
            "metrics": {"nse": 0.91},
        }
        (outcomes_dir / "data_audit.latest.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        source_report = {
            "agent_results": [
                {
                    "agent_id": "tanyuan",
                    "agent_name": "探源",
                    "workflow_results": [{"workflow_key": "data_audit"}],
                }
            ]
        }
        (contracts_dir / "source_report.json").write_text(
            json.dumps(source_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        state = {
            "run_id": "live-ut-html",
            "case_id": case_id,
            "started_at": "2026-04-02T00:00:00+00:00",
            "last_updated_at": "2026-04-02T00:00:01+00:00",
            "execution_profile": "fast_validation",
            "retry": {"max_retries": 1},
            "source_report": str(contracts_dir / "source_report.json"),
            "summary": {"total": 1, "passed": 1, "failed": 0, "timeout": 0, "pending": 0, "retries_used": 0, "outcomes_generated": 1, "outcome_coverage": 1.0},
            "current": None,
            "records": [
                {
                    "agent_id": "tanyuan",
                    "agent_name": "探源",
                    "workflow_key": "data_audit",
                    "status": "passed",
                    "started_at": "2026-04-02T00:00:00+00:00",
                    "ended_at": "2026-04-02T00:00:01+00:00",
                    "duration_s": 1.0,
                    "attempts": 1,
                    "excerpt": "{}",
                }
            ],
        }

        try:
            _render_dashboard_html(html_path, state)
            content = html_path.read_text(encoding="utf-8")
            self.assertIn("Agent 结果工作面", content)
            self.assertIn("workflow-nav-btn", content)
            self.assertIn("workflow-detail-panel", content)
            self.assertIn("timeline-title", content)
            self.assertIn("data_audit", content)
            self.assertIn("数据审计已完成", content)
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
