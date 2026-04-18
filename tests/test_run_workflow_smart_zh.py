"""轻量测试：拓扑排序与 allow_registry_only（不跑可行性导出）；Smart CLI meta / JSON 摘要契约。"""
from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows import run_workflow_smart_zh as target
from workflows.run_workflow_smart_zh import (
    _agent_json_summary_requested,
    _build_cli_result_payload,
    _coerce_catalog_string_list,
    _coerce_continue_on_outcome_statuses,
    _recommended_commands_for_business,
    _resolve_plan_report_level,
    _resolve_run_report_level,
    _save_run_summary,
    _scoped_cli_result_relpath,
    _should_refresh_shared_cli_result,
    _summarize_workflow_result,
    _topo_sort_selected,
    _workflow_meta_from_catalog,
    _write_and_maybe_print_cli_result,
    build_auto_plan,
    build_parser,
    cmd_meta,
    cmd_plan,
    cmd_run,
)


def test_topo_sort_orders_dependencies_before_dependents() -> None:
    catalog: dict = {
        "defaults": {"scopes": ["modeling"], "priority": 50, "auto_select": True},
        "workflows": {
            "model": {"display_zh": "水文建模", "priority": 30, "run_after": []},
            "calibrate": {"display_zh": "率定", "priority": 35, "run_after": ["model"]},
        },
    }
    ordered, warnings = _topo_sort_selected({"model", "calibrate"}, catalog)
    assert not warnings
    assert ordered.index("model") < ordered.index("calibrate")


def test_topo_sort_cycle_falls_back_and_warns() -> None:
    catalog: dict = {
        "defaults": {"scopes": ["modeling"], "priority": 50, "auto_select": True},
        "workflows": {
            "a": {"display_zh": "A", "priority": 10, "run_after": ["b"]},
            "b": {"display_zh": "B", "priority": 20, "run_after": ["a"]},
        },
    }
    ordered, warnings = _topo_sort_selected({"a", "b"}, catalog)
    assert len(warnings) == 1
    assert "回退" in warnings[0]
    assert set(ordered) == {"a", "b"}


def test_actual_catalog_orders_hyd_cal_and_hyd_report_before_coupled() -> None:
    catalog = target.load_catalog()

    ordered, warnings = _topo_sort_selected(
        {"model", "section_analysis", "hyd_cal", "hyd_report", "coupled"},
        catalog,
    )

    assert not warnings
    assert ordered.index("hyd_cal") < ordered.index("hyd_report")
    assert ordered.index("hyd_cal") < ordered.index("coupled")


def test_actual_catalog_marks_data_audit_degraded_as_non_blocking() -> None:
    catalog = target.load_catalog()

    meta = _workflow_meta_from_catalog(catalog, "data_audit")

    assert meta["continue_on_outcome_statuses"] == ["degraded"]


def test_actual_catalog_marks_coupled_degraded_as_non_blocking() -> None:
    catalog = target.load_catalog()

    meta = _workflow_meta_from_catalog(catalog, "coupled")

    assert meta["continue_on_outcome_statuses"] == ["degraded"]


def test_actual_catalog_marks_hyd_cal_degraded_as_non_blocking() -> None:
    catalog = target.load_catalog()

    meta = _workflow_meta_from_catalog(catalog, "hyd_cal")

    assert meta["continue_on_outcome_statuses"] == ["degraded"]


def test_coerce_catalog_string_list_accepts_string_scalar() -> None:
    assert _coerce_catalog_string_list("model", field_name="run_after") == ["model"]


def test_coerce_continue_on_outcome_statuses_accepts_string_scalar() -> None:
    assert _coerce_continue_on_outcome_statuses("degraded") == ["degraded"]


def test_coerce_continue_on_outcome_statuses_rejects_invalid_mapping() -> None:
    with pytest.raises(ValueError, match="continue_on_outcome_statuses"):
        _coerce_continue_on_outcome_statuses({"status": "degraded"})


def test_coerce_continue_on_outcome_statuses_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="未知状态"):
        _coerce_continue_on_outcome_statuses(["degrded"])


def test_workflow_meta_accepts_scalar_run_after() -> None:
    meta = _workflow_meta_from_catalog(
        {"workflows": {"model": {"run_after": "init"}}},
        "model",
    )

    assert meta["run_after"] == ["init"]


def test_workflow_meta_allows_empty_override_to_disable_default_continue_statuses() -> None:
    meta = _workflow_meta_from_catalog(
        {
            "defaults": {"continue_on_outcome_statuses": ["degraded", "partial"]},
            "workflows": {"model": {"continue_on_outcome_statuses": []}},
        },
        "model",
    )

    assert meta["continue_on_outcome_statuses"] == []


def test_allow_registry_only_includes_tier_registry_only() -> None:
    catalog: dict = {
        "defaults": {"scopes": ["modeling"], "priority": 50, "auto_select": True},
        "workflows": {
            "model": {"display_zh": "水文建模", "priority": 30},
            "hydro_report": {"display_zh": "水文报告", "priority": 40},
        },
    }
    feasibility = {
        "workflows": [
            {"key": "model", "tier": "data_ok"},
            {"key": "hydro_report", "tier": "registry_only"},
        ]
    }
    hints_payload = {"hints": {"suggested_workflows": ["hydro_report", "model"]}}

    off = build_auto_plan(
        "ut_case",
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )
    keys_off = [r["workflow_key"] for r in off["workflows"]]
    assert "model" in keys_off
    assert "hydro_report" not in keys_off
    assert off["allow_registry_only"] is False

    on = build_auto_plan(
        "ut_case",
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=True,
    )
    keys_on = [r["workflow_key"] for r in on["workflows"]]
    assert "model" in keys_on
    assert "hydro_report" in keys_on
    assert on["allow_registry_only"] is True
    assert "hydro_report" in (on.get("registry_only_keys_included") or [])


def test_build_auto_plan_smart_excludes_control_only_workflows() -> None:
    catalog: dict = {
        "defaults": {"scopes": ["modeling"], "priority": 50, "auto_select": True, "external": False, "long_running": False},
        "workflows": {
            "model": {"display_zh": "水文建模", "priority": 30, "scopes": ["modeling"]},
            "cascade": {"display_zh": "梯级全自主运行", "priority": 70, "scopes": ["control", "evaluation"]},
        },
    }
    feasibility = {
        "workflows": [
            {"key": "model", "tier": "data_ok"},
            {"key": "cascade", "tier": "data_ok"},
        ]
    }
    hints_payload = {"hints": {"suggested_workflows": ["cascade", "model"]}}

    plan = build_auto_plan(
        "ut_case",
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert [row["workflow_key"] for row in plan["workflows"]] == ["model"]


def test_build_auto_plan_full_keeps_control_workflows() -> None:
    catalog: dict = {
        "defaults": {"scopes": ["modeling"], "priority": 50, "auto_select": True, "external": False, "long_running": False},
        "workflows": {
            "model": {"display_zh": "水文建模", "priority": 30, "scopes": ["modeling"]},
            "cascade": {"display_zh": "梯级全自主运行", "priority": 70, "scopes": ["control", "evaluation"]},
        },
    }
    feasibility = {
        "workflows": [
            {"key": "model", "tier": "data_ok"},
            {"key": "cascade", "tier": "data_ok"},
        ]
    }
    hints_payload = {"hints": {"suggested_workflows": ["cascade", "model"]}}

    plan = build_auto_plan(
        "ut_case",
        catalog=catalog,
        feasibility=feasibility,
        hints_payload=hints_payload,
        profile="full",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert [row["workflow_key"] for row in plan["workflows"]] == ["model", "cascade"]


def test_build_auto_plan_expands_run_after_dependencies_for_selected_workflow() -> None:
    catalog = target.load_catalog()

    plan = build_auto_plan(
        "demo",
        catalog=catalog,
        feasibility={
            "workflows": [
                {"key": "section_analysis", "tier": "data_ok"},
                {"key": "hyd_cal", "tier": "data_ok"},
                {"key": "hyd_report", "tier": "data_ok"},
            ]
        },
        hints_payload={"hints": {"suggested_workflows": ["hyd_report"]}},
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert [row["workflow_key"] for row in plan["workflows"]] == ["section_analysis", "hyd_cal", "hyd_report"]


def test_build_auto_plan_removes_workflow_with_unsatisfied_run_after_dependencies() -> None:
    catalog = target.load_catalog()

    plan = build_auto_plan(
        "demo",
        catalog=catalog,
        feasibility={"workflows": [{"key": "hyd_report", "tier": "data_ok"}]},
        hints_payload={"hints": {"suggested_workflows": ["hyd_report"]}},
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert plan["workflows"] == []
    assert any("hyd_report" in note and "前置依赖" in note for note in plan["notes_zh"])


def test_actual_feasibility_excludes_false_positive_hyd_cal_and_calibrate_from_smart_plan() -> None:
    catalog = target.load_catalog()

    for case_id in ("xuhonghe", "jiaodongtiaoshui", "zhongxian"):
        feasibility = target.run_feasibility_export(case_id, target.DEFAULT_RULES)
        rows = {row["key"]: row for row in (feasibility.get("workflows") or [])}
        assert rows["hyd_cal"]["tier"] == "data_gap"
        assert rows["calibrate"]["tier"] == "data_gap"

        plan = build_auto_plan(
            case_id,
            catalog=catalog,
            feasibility=feasibility,
            hints_payload={"hints": {"suggested_workflows": ["hyd_cal", "calibrate", "model"]}},
            profile="smart",
            include_external=False,
            include_long_running=False,
            max_workflows=20,
            allow_registry_only=False,
        )
        selected = [row["workflow_key"] for row in plan["workflows"]]
        assert "hyd_cal" not in selected
        assert "calibrate" not in selected


def test_actual_feasibility_removes_calibrate_when_model_dependency_is_not_ready() -> None:
    catalog = target.load_catalog()
    feasibility = target.run_feasibility_export("yinchuojiliao", target.DEFAULT_RULES)
    rows = {row["key"]: row for row in (feasibility.get("workflows") or [])}
    assert rows["model"]["tier"] == "unsupported"
    assert rows["hyd_cal"]["tier"] == "data_gap"
    assert rows["calibrate"]["tier"] == "data_ok"

    plan = build_auto_plan(
        "yinchuojiliao",
        catalog=catalog,
        feasibility=feasibility,
        hints_payload={"hints": {"suggested_workflows": ["hyd_cal", "calibrate", "model"]}},
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=20,
        allow_registry_only=False,
    )
    selected = [row["workflow_key"] for row in plan["workflows"]]
    assert "hyd_cal" not in selected
    assert "calibrate" not in selected
    assert any("calibrate" in note and "前置依赖 model" in note for note in plan["notes_zh"])


def test_actual_catalog_excludes_hyd_sim_without_parameter_governance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = target.load_catalog()
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    plan = build_auto_plan(
        "demo",
        catalog=catalog,
        feasibility={
            "workflows": [
                {"key": "model", "tier": "data_ok"},
                {"key": "section_analysis", "tier": "data_ok"},
                {"key": "hyd_sim", "tier": "data_ok"},
            ]
        },
        hints_payload={"hints": {"suggested_workflows": ["hyd_sim", "model", "section_analysis"]}},
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert [row["workflow_key"] for row in plan["workflows"]] == ["model", "section_analysis"]


def test_actual_catalog_includes_hyd_sim_with_parameter_governance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = target.load_catalog()
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    contracts_dir = tmp_path / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / "parameter_governance.latest.json").write_text("{}", encoding="utf-8")

    plan = build_auto_plan(
        "demo",
        catalog=catalog,
        feasibility={
            "workflows": [
                {"key": "model", "tier": "data_ok"},
                {"key": "section_analysis", "tier": "data_ok"},
                {"key": "hyd_sim", "tier": "data_ok"},
            ]
        },
        hints_payload={"hints": {"suggested_workflows": ["hyd_sim", "model", "section_analysis"]}},
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=10,
        allow_registry_only=False,
    )

    assert [row["workflow_key"] for row in plan["workflows"]] == ["model", "section_analysis", "hyd_sim"]


def _ns(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "no_reports": False,
        "no_detailed_reports": False,
        "simple_report": False,
        "report_level": "detailed",
        "no_plan_reports": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_resolve_run_report_level_defaults_and_flags() -> None:
    assert _resolve_run_report_level(_ns()) == "detailed"
    assert _resolve_run_report_level(_ns(report_level="simple")) == "simple"
    assert _resolve_run_report_level(_ns(report_level="none")) == "none"
    assert _resolve_run_report_level(_ns(no_reports=True)) == "none"
    assert _resolve_run_report_level(_ns(no_detailed_reports=True)) == "none"
    assert _resolve_run_report_level(_ns(simple_report=True)) == "simple"
    assert _resolve_run_report_level(_ns(no_reports=True, simple_report=True)) == "none"


def test_resolve_plan_report_level_respects_no_plan_reports() -> None:
    assert _resolve_plan_report_level(_ns(no_plan_reports=True, report_level="detailed")) == "none"
    assert _resolve_plan_report_level(_ns(no_plan_reports=False, report_level="simple")) == "simple"


def test_cmd_meta_json_has_schema_and_subcommands() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_meta(argparse.Namespace(catalog=""))
    assert rc == 0
    meta = json.loads(buf.getvalue())
    assert meta.get("schema_version") == "workflow_smart_cli_meta.v1"
    assert meta.get("cli_module") == "workflows.run_workflow_smart_zh"
    assert "exit_codes" in meta and "0" in meta["exit_codes"]
    names = {s["name"] for s in (meta.get("subcommands") or [])}
    assert {"meta", "plan", "run", "refresh-reports"}.issubset(names)
    assert "artifacts_relative" in meta
    assert "cli_result" in (meta["artifacts_relative"] or {})


def test_agent_json_summary_requested_flag_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    ns = argparse.Namespace(json_summary=False)
    monkeypatch.delenv("HYDRO_SMART_JSON_SUMMARY", raising=False)
    assert _agent_json_summary_requested(ns) is False
    monkeypatch.setenv("HYDRO_SMART_JSON_SUMMARY", "1")
    assert _agent_json_summary_requested(ns) is True
    monkeypatch.setenv("HYDRO_SMART_JSON_SUMMARY", "false")
    assert _agent_json_summary_requested(ns) is False
    ns2 = argparse.Namespace(json_summary=True)
    assert _agent_json_summary_requested(ns2) is True


def test_scoped_cli_result_relpath_encodes_command_profile_and_dry_run() -> None:
    assert (
        _scoped_cli_result_relpath("demo", command="run", profile="smart", dry_run=False)
        == "cases/demo/contracts/workflow_smart_cli_result.run.smart.latest.json"
    )
    assert (
        _scoped_cli_result_relpath("demo", command="refresh-reports", profile="", dry_run=True)
        == "cases/demo/contracts/workflow_smart_cli_result.refresh_reports.no_profile.dry_run.latest.json"
    )



def test_should_refresh_shared_cli_result_only_for_formal_smart_run() -> None:
    assert _should_refresh_shared_cli_result(command="run", profile="smart", dry_run=False) is True
    assert _should_refresh_shared_cli_result(command="run", profile="smart", dry_run=True) is False
    assert _should_refresh_shared_cli_result(command="run", profile="full", dry_run=False) is False
    assert _should_refresh_shared_cli_result(command="plan", profile="smart", dry_run=False) is False



def test_build_cli_result_payload_plan_shape() -> None:
    plan = {"workflows": [{"workflow_key": "init"}]}
    p = _build_cli_result_payload(
        command="plan",
        case_id="c",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[],
        failures=[],
        total_elapsed_sec=0.5,
        plan=plan,
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["command"] == "plan"
    assert p["steps_planned"] == 1 and p["steps_executed"] == 0 and p["steps_ok"] == 0
    assert p["profile_label_zh"] == "一键建模"
    assert p["business_goal"] == "一键建模（plan）"
    assert p["business_status_zh"] == "一键建模计划已生成"
    assert p["error_code"] is None
    assert p["error_category"] is None
    assert p["ready_for_review"] is False
    assert p["ready_for_release"] is False
    assert p["artifacts"]["cli_result_scoped"] == "cases/c/contracts/workflow_smart_cli_result.plan.smart.latest.json"
    assert "cases/c/contracts/workflow_smart_cli_result.plan.smart.latest.json" in p["recommended_artifacts"]
    assert "cases/<case_id>/contracts/workflow_smart_plan_report.latest.md" in p["recommended_artifacts"]
    assert p["recommended_next_action"]



def test_recommended_commands_for_business_cover_common_next_steps() -> None:
    assert _recommended_commands_for_business(command="plan", case_id="daduhe", profile="smart") == [
        "python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --profile smart --dry-run --json-summary",
        "python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --profile smart --json-summary",
    ]
    assert _recommended_commands_for_business(command="run", case_id="daduhe", profile="smart") == [
        "python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id daduhe --json-summary",
        "python3 -m workflows.run_workflow_smart_zh plan --case-id daduhe --json-summary",
    ]



def test_build_cli_result_payload_includes_business_next_step_commands() -> None:
    payload = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=1,
        ok=False,
        results=[{"workflow_key": "model", "ok": False}],
        failures=["model: FileNotFoundError: missing source bundle"],
        total_elapsed_sec=1.2,
        plan={"workflows": [{"workflow_key": "model"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert payload["recommended_next_commands"] == [
        "python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id x --json-summary",
        "python3 -m workflows.run_workflow_smart_zh plan --case-id x --json-summary",
    ]



def test_build_parser_help_mentions_business_quick_start() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "业务人员快速开始" in help_text
    assert "先执行 legend，再 plan，再 run" in help_text
    assert "改文案后 refresh-reports" in help_text



def test_build_parser_subcommand_help_is_business_friendly() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "legend" in help_text
    assert "先看系统支持什么" in help_text
    assert "list" in help_text
    assert "看当前可用工作流清单" in help_text
    assert "plan" in help_text
    assert "先出执行计划" in help_text
    assert "run" in help_text
    assert "按计划正式执行" in help_text
    assert "refresh-reports" in help_text
    assert "不重跑，只重出报告" in help_text



def test_cmd_legend_prints_business_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.load_catalog",
        lambda _path=None: {
            "e2e_scopes_zh": {"modeling": "建模相关"},
            "profiles_help_zh": {"smart": "一键建模"},
            "user_prompt_examples_zh": ["帮我先出计划"],
        },
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = target.cmd_legend(argparse.Namespace(catalog=""))
    output = buf.getvalue()
    assert rc == 0
    assert "业务人员建议按这个顺序使用" in output
    assert "先执行 legend / list" in output
    assert "按适用模式执行 run" in output
    assert "refresh-reports" in output
    assert "帮我先出计划" in output



def test_format_scope_labels_handles_empty_and_unknown_values() -> None:
    assert target._format_scope_labels(None) == "未标注"
    assert target._format_scope_labels([]) == "未标注"
    assert target._format_scope_labels(["smart", "smart", "evaluation"]) == "一键建模 / 结果审查"
    assert target._format_scope_labels(["unknown"]) == "unknown"
    assert target._format_scope_labels(["", "  ", "smart"]) == "一键建模"



def test_cmd_list_prints_business_scope_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {})
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.list_workflows_zh",
        lambda _catalog=None: [
            {
                "name": "model",
                "display_zh": "水文建模",
                "category_zh": "建模",
                "scopes": ["smart", "evaluation"],
                "description": "生成建模结果",
            }
        ],
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = target.cmd_list(argparse.Namespace(catalog=""))
    output = buf.getvalue()
    assert rc == 0
    assert "适用模式=一键建模 / 结果审查" in output
    assert "业务场景：一键建模 / 结果审查" in output
    assert "生成建模结果" in output



def test_print_cli_result_guidance_prints_business_status_and_commands(capsys: pytest.CaptureFixture[str]) -> None:
    target._print_cli_result_guidance(
        {
            "business_status_zh": "一键建模执行未完成",
            "recommended_next_action": "补齐输入后重新执行。",
            "recommended_next_commands": [
                "python3 -m workflows.run_workflow_smart_zh plan --case-id x --json-summary",
            ],
        }
    )

    out = capsys.readouterr().out
    assert "业务状态：一键建模执行未完成" in out
    assert "建议处理：补齐输入后重新执行。" in out
    assert "建议命令：" in out
    assert "python3 -m workflows.run_workflow_smart_zh plan --case-id x --json-summary" in out


def test_build_cli_result_payload_run_success_shape() -> None:
    plan = {"workflows": [{"workflow_key": "init"}, {"workflow_key": "model"}]}
    results = [
        {"workflow_key": "init", "ok": True},
        {"workflow_key": "model", "ok": True},
    ]
    bundle = {
        "report_paths": {
            "a": "cases/x/contracts/a.md",
            "business_run_digest_md": "cases/x/contracts/business_run_digest.latest.md",
        },
        "reporting_config_source": "merged",
    }
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=0,
        ok=True,
        results=results,
        failures=[],
        total_elapsed_sec=12.3456,
        plan=plan,
        report_bundle=bundle,
        dry_run=False,
        progress_relpath="cases/x/contracts/workflow_smart_progress.latest.ndjson",
        md_refresh=None,
    )
    assert p["schema_version"] == "workflow_smart_cli_result.v1"
    assert p["command"] == "run" and p["case_id"] == "x"
    assert p["steps_planned"] == 2 and p["steps_executed"] == 2 and p["steps_ok"] == 2
    assert p["artifacts"]["progress_ndjson"] == "cases/x/contracts/workflow_smart_progress.latest.ndjson"
    assert p["report_paths"]["a"] == "cases/x/contracts/a.md"
    assert p["reporting_config_source"] == "merged"
    assert p["profile_label_zh"] == "一键建模"
    assert p["business_goal"] == "一键建模（run）"
    assert p["business_status_zh"] == "一键建模执行完成"
    assert p["error_code"] is None
    assert p["error_category"] is None
    assert p["ready_for_review"] is True
    assert p["ready_for_release"] is False
    assert p["artifacts"]["cli_result_scoped"] == "cases/x/contracts/workflow_smart_cli_result.run.smart.latest.json"
    assert "cases/x/contracts/workflow_smart_cli_result.run.smart.latest.json" in p["recommended_artifacts"]
    assert "cases/x/contracts/business_run_digest.latest.md" in p["recommended_artifacts"]
    assert p["recommended_next_action"]


def test_build_cli_result_payload_run_failure_classifies_missing_input() -> None:
    plan = {"workflows": [{"workflow_key": "model"}]}
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="modeling",
        exit_code=1,
        ok=False,
        results=[{"workflow_key": "model", "ok": False}],
        failures=["model: FileNotFoundError: missing source bundle"],
        total_elapsed_sec=1.2,
        plan=plan,
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["profile_label_zh"] == "建模分析"
    assert p["business_status_zh"] == "建模分析执行未完成"
    assert p["error_code"] == "smart_run_missing_input"
    assert p["error_category"] == "input"
    assert p["ready_for_review"] is False
    assert p["ready_for_release"] is False


def test_build_cli_result_payload_refresh_reports_success_is_release_ready() -> None:
    p = _build_cli_result_payload(
        command="refresh-reports",
        case_id="x",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[{"workflow_key": "model", "ok": True}],
        failures=[],
        total_elapsed_sec=None,
        plan={"workflows": [{"workflow_key": "model"}]},
        report_bundle={"report_paths": {"final_report_json": "cases/x/contracts/final_report.latest.json"}},
        dry_run=False,
        progress_relpath="cases/x/contracts/workflow_smart_progress.latest.ndjson",
        md_refresh=None,
    )
    assert p["business_status_zh"] == "报告链已刷新"
    assert p["ready_for_review"] is True
    assert p["ready_for_release"] is True
    assert p["error_code"] is None


def test_build_cli_result_payload_run_quality_degraded_sets_quality_error() -> None:
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=1,
        ok=False,
        results=[{"workflow_key": "cascade", "ok": False}],
        failures=["cascade: quality_failed: 控制总体通过率未达标"],
        total_elapsed_sec=3.2,
        plan={"workflows": [{"workflow_key": "cascade"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath="cases/x/contracts/workflow_smart_progress.latest.ndjson",
        md_refresh=None,
    )
    assert p["business_status_zh"] == "一键建模执行已落盘，但未达到业务质量门槛"
    assert p["error_code"] == "smart_run_quality_degraded"
    assert p["error_category"] == "quality"
    assert p["ready_for_review"] is False
    assert p["ready_for_release"] is False


def test_build_cli_result_payload_run_degraded_sets_quality_error() -> None:
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=1,
        ok=False,
        results=[{"workflow_key": "cascade", "ok": False}],
        failures=["cascade: degraded: 部分阶段未达产品门槛"],
        total_elapsed_sec=2.4,
        plan={"workflows": [{"workflow_key": "cascade"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["error_code"] == "smart_run_quality_degraded"
    assert p["error_category"] == "quality"


def test_build_cli_result_payload_non_blocking_degraded_is_not_review_ready() -> None:
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[
            {
                "workflow_key": "data_audit",
                "ok": False,
                "outcome_status": "degraded",
                "continued": True,
                "continue_reason": "catalog_non_blocking_status",
            }
        ],
        failures=[],
        total_elapsed_sec=1.5,
        plan={"workflows": [{"workflow_key": "data_audit"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["error_code"] == "smart_run_non_blocking_degraded"
    assert p["ready_for_review"] is False
    assert p["ready_for_release"] is False



def test_build_cli_result_payload_collects_continued_degraded_steps() -> None:
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[
            {
                "workflow_key": "data_audit",
                "ok": False,
                "outcome_status": "degraded",
                "continued": True,
                "continue_reason": "catalog_non_blocking_status",
                "business_status_zh": "已输出降级版数据审计结果。",
                "recommended_next_action": "补充 SQLite 后重跑。",
                "artifact_guidance": [{"artifact": "data_quality_audit.latest.json", "purpose": "查看降级原因。"}],
            },
            {"workflow_key": "model", "ok": True, "outcome_status": "completed"},
        ],
        failures=["data_audit: degraded: 未发现可审计 SQLite"],
        total_elapsed_sec=2.4,
        plan={"workflows": [{"workflow_key": "data_audit"}, {"workflow_key": "model"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["error_code"] == "smart_run_non_blocking_degraded"
    assert p["continued_step_count"] == 1
    assert p["continued_quality_degraded_steps"][0]["workflow_key"] == "data_audit"
    assert p["continued_quality_degraded_steps"][0]["artifact_guidance"][0]["artifact"] == "data_quality_audit.latest.json"


def test_build_cli_result_payload_prefers_hard_failure_over_non_blocking_degraded() -> None:
    p = _build_cli_result_payload(
        command="run",
        case_id="x",
        profile="smart",
        exit_code=1,
        ok=False,
        results=[
            {
                "workflow_key": "data_audit",
                "ok": False,
                "outcome_status": "degraded",
                "continued": True,
                "continue_reason": "catalog_non_blocking_status",
            },
            {
                "workflow_key": "model",
                "ok": False,
                "outcome_status": "failed",
            },
        ],
        failures=["model: runtime error"],
        total_elapsed_sec=2.4,
        plan={"workflows": [{"workflow_key": "data_audit"}, {"workflow_key": "model"}]},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )
    assert p["error_code"] == "smart_run_workflow_failed"
    assert p["error_category"] == "workflow_execution"
    assert p["continued_step_count"] == 1
    assert p["ready_for_review"] is False


def test_summarize_workflow_result_uses_status_when_outcome_missing() -> None:
    summary = _summarize_workflow_result(
        {
            "status": "partial",
            "quality_gate_passed": False,
            "quality_reason": "source_discovery failed",
        }
    )

    assert summary["ok"] is False
    assert summary["outcome_status"] == "partial"
    assert summary["quality_gate_passed"] is False
    assert summary["quality_reason"] == "source_discovery failed"



def test_cmd_run_continues_for_catalog_marked_non_blocking_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {
        "workflows": {
            "data_audit": {"continue_on_outcome_statuses": ["degraded"]},
            "model": {},
        }
    })
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", lambda *_args, **_kwargs: {"hints": {}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.build_auto_plan",
        lambda *_args, **_kwargs: {
            "workflows": [
                {"workflow_key": "data_audit", "display_zh": "数据质量审计"},
                {"workflow_key": "model", "display_zh": "水文建模"},
            ]
        },
    )

    def fake_run_workflow(key: str, *, case_id: str) -> dict[str, object]:
        calls.append(key)
        if key == "data_audit":
            return {
                "outcome_status": "degraded",
                "quality_gate_passed": False,
                "quality_reason": "未发现可审计 SQLite",
            }
        return {"status": "completed"}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_workflow", fake_run_workflow)

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="",
        rules="",
        config="",
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        no_save=True,
        dry_run=False,
        json_summary=False,
        print_json_summary=False,
        no_progress_file=True,
        progress_file="",
        continue_on_error=False,
        verbose=False,
        report_level="none",
        no_reports=True,
        no_detailed_reports=False,
        simple_report=False,
        smart_reporting_config="",
        case_config="",
        skip_universal_report=False,
    )

    assert cmd_run(ns) == 0
    assert calls == ["data_audit", "model"]



def test_cmd_run_stops_for_blocking_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {"workflows": {"data_audit": {}, "model": {}}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", lambda *_args, **_kwargs: {"hints": {}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.build_auto_plan",
        lambda *_args, **_kwargs: {
            "workflows": [
                {"workflow_key": "data_audit", "display_zh": "数据质量审计"},
                {"workflow_key": "model", "display_zh": "水文建模"},
            ]
        },
    )

    def fake_run_workflow(key: str, *, case_id: str) -> dict[str, object]:
        calls.append(key)
        if key == "data_audit":
            return {
                "outcome_status": "degraded",
                "quality_gate_passed": False,
                "quality_reason": "未发现可审计 SQLite",
            }
        return {"status": "completed"}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_workflow", fake_run_workflow)

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="",
        rules="",
        config="",
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        no_save=True,
        dry_run=False,
        json_summary=False,
        print_json_summary=False,
        no_progress_file=True,
        progress_file="",
        continue_on_error=False,
        verbose=False,
        report_level="none",
        no_reports=True,
        no_detailed_reports=False,
        simple_report=False,
        smart_reporting_config="",
        case_config="",
        skip_universal_report=False,
    )

    assert cmd_run(ns) == 1
    assert calls == ["data_audit"]


def test_cmd_run_continues_from_degraded_hyd_cal_to_hyd_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.load_catalog",
        lambda _path=None: {
            "workflows": {
                "hyd_cal": {"continue_on_outcome_statuses": ["degraded"]},
                "hyd_report": {},
            }
        },
    )
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", lambda *_args, **_kwargs: {"hints": {}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "workflows.run_workflow_smart_zh.build_auto_plan",
        lambda *_args, **_kwargs: {
            "workflows": [
                {"workflow_key": "hyd_cal", "display_zh": "水力学率定验证"},
                {"workflow_key": "hyd_report", "display_zh": "D2 水力学精度报告"},
            ]
        },
    )

    def fake_run_workflow(key: str, *, case_id: str) -> dict[str, object]:
        calls.append(key)
        if key == "hyd_cal":
            return {
                "outcome_status": "degraded",
                "quality_gate_passed": False,
                "quality_reason": "部分候选站点完成率定，部分站点失败；请检查 station_results 明细",
                "artifact_guidance": [
                    {
                        "artifact": "hydraulic_calibration.latest.json",
                        "purpose": "确认 station_results[*].calibration.best 是否已生成。",
                    }
                ],
            }
        return {"status": "completed"}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_workflow", fake_run_workflow)

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="",
        rules="",
        config="",
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        no_save=True,
        dry_run=False,
        json_summary=False,
        print_json_summary=False,
        no_progress_file=True,
        progress_file="",
        continue_on_error=False,
        verbose=False,
        report_level="none",
        no_reports=True,
        no_detailed_reports=False,
        simple_report=False,
        smart_reporting_config="",
        case_config="",
        skip_universal_report=False,
    )

    assert cmd_run(ns) == 0
    assert calls == ["hyd_cal", "hyd_report"]



def test_write_and_maybe_print_cli_result_writes_scoped_and_refreshes_shared_for_formal_smart_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    args = SimpleNamespace(json_summary=True, print_json_summary=False)
    payload = _build_cli_result_payload(
        command="run",
        case_id="demo",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[],
        failures=[],
        total_elapsed_sec=1.0,
        plan={"workflows": []},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )

    _write_and_maybe_print_cli_result(args, "demo", payload)

    scoped_path = tmp_path / payload["artifacts"]["cli_result_scoped"]
    shared_path = tmp_path / payload["artifacts"]["cli_result"]
    assert scoped_path.is_file()
    assert shared_path.is_file()
    assert json.loads(scoped_path.read_text(encoding="utf-8"))["profile"] == "smart"
    assert json.loads(shared_path.read_text(encoding="utf-8"))["profile"] == "smart"



def test_write_and_maybe_print_cli_result_dry_run_does_not_refresh_shared_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    contracts_dir = tmp_path / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    shared_path = contracts_dir / "workflow_smart_cli_result.latest.json"
    shared_path.write_text(json.dumps({"profile": "smart", "dry_run": False}), encoding="utf-8")
    args = SimpleNamespace(json_summary=True, print_json_summary=False)
    payload = _build_cli_result_payload(
        command="run",
        case_id="demo",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[],
        failures=[],
        total_elapsed_sec=0.1,
        plan={"workflows": []},
        report_bundle=None,
        dry_run=True,
        progress_relpath=None,
        md_refresh=None,
    )

    _write_and_maybe_print_cli_result(args, "demo", payload)

    scoped_path = tmp_path / payload["artifacts"]["cli_result_scoped"]
    assert scoped_path.is_file()
    assert json.loads(scoped_path.read_text(encoding="utf-8"))["dry_run"] is True
    assert json.loads(shared_path.read_text(encoding="utf-8")) == {"profile": "smart", "dry_run": False}



def test_write_and_maybe_print_cli_result_plan_does_not_refresh_shared_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    contracts_dir = tmp_path / "cases" / "demo" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    shared_path = contracts_dir / "workflow_smart_cli_result.latest.json"
    shared_path.write_text(json.dumps({"command": "run", "profile": "smart"}), encoding="utf-8")
    args = SimpleNamespace(json_summary=True, print_json_summary=False)
    payload = _build_cli_result_payload(
        command="plan",
        case_id="demo",
        profile="smart",
        exit_code=0,
        ok=True,
        results=[],
        failures=[],
        total_elapsed_sec=0.1,
        plan={"workflows": []},
        report_bundle=None,
        dry_run=False,
        progress_relpath=None,
        md_refresh=None,
    )

    _write_and_maybe_print_cli_result(args, "demo", payload)

    scoped_path = tmp_path / payload["artifacts"]["cli_result_scoped"]
    assert scoped_path.is_file()
    assert json.loads(scoped_path.read_text(encoding="utf-8"))["command"] == "plan"
    assert json.loads(shared_path.read_text(encoding="utf-8")) == {"command": "run", "profile": "smart"}


def test_save_run_summary_marks_non_blocking_degraded_as_not_fully_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(target, "WORKSPACE", tmp_path)

    path = _save_run_summary(
        "demo",
        "smart",
        results=[
            {
                "workflow_key": "hyd_cal",
                "ok": False,
                "outcome_status": "degraded",
                "continued": True,
                "continue_reason": "catalog_non_blocking_status",
            },
            {"workflow_key": "hyd_report", "ok": True, "outcome_status": "completed"},
        ],
        failures=[],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["has_non_blocking_degraded"] is True
    assert payload["continued_degraded_step_count"] == 1
    assert payload["continued_degraded_steps"][0]["workflow_key"] == "hyd_cal"



def test_cmd_plan_passes_restrict_workflow_keys_to_build_auto_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", lambda *_args, **_kwargs: {"hints": {}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_scope_legend", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)

    def fake_build_auto_plan(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"workflows": []}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.build_auto_plan", fake_build_auto_plan)

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="init,model",
        rules="",
        config="",
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        json=False,
        no_save=True,
        report_level="none",
        no_plan_reports=True,
        json_summary=False,
        print_json_summary=False,
        smart_reporting_config="",
        case_config="",
    )

    assert cmd_plan(ns) == 0
    assert captured["kwargs"]["restrict_workflow_keys"] == {"init", "model"}


def test_cmd_run_passes_restrict_workflow_keys_to_build_auto_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", lambda *_args, **_kwargs: {"hints": {}})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)

    def fake_build_auto_plan(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"workflows": []}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.build_auto_plan", fake_build_auto_plan)

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="init,model",
        rules="",
        config="",
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        no_save=True,
        dry_run=True,
        json_summary=False,
        print_json_summary=False,
        no_progress_file=True,
        progress_file="",
        continue_on_error=False,
        verbose=False,
        report_level="none",
        no_reports=True,
        no_detailed_reports=False,
        simple_report=False,
        smart_reporting_config="",
        case_config="",
    )

    assert cmd_run(ns) == 0
    assert captured["kwargs"]["restrict_workflow_keys"] == {"init", "model"}


def test_cmd_run_resolves_relative_config_against_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    rel_config = "configs/local_loop.yaml"
    cfg_path = tmp_path / rel_config
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("loop: true\n", encoding="utf-8")

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr("workflows.run_workflow_smart_zh.load_catalog", lambda _path=None: {})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_feasibility_export", lambda *_args, **_kwargs: {"workflows": []})
    monkeypatch.setattr("workflows.run_workflow_smart_zh.print_plan_table", lambda *_args, **_kwargs: None)

    def fake_run_modeling_hints(case_id: str, config_path: Path, rules_path: Path) -> dict[str, object]:
        captured["config_path"] = config_path
        return {"hints": {}}

    monkeypatch.setattr("workflows.run_workflow_smart_zh.run_modeling_hints", fake_run_modeling_hints)
    monkeypatch.setattr("workflows.run_workflow_smart_zh.build_auto_plan", lambda *_args, **_kwargs: {"workflows": []})

    ns = argparse.Namespace(
        catalog="",
        restrict_workflow_keys="",
        rules="",
        config=rel_config,
        case_id="demo",
        profile="smart",
        include_external=False,
        include_long_running=False,
        max_workflows=5,
        allow_registry_only=False,
        no_save=True,
        dry_run=True,
        json_summary=False,
        print_json_summary=False,
        no_progress_file=True,
        progress_file="",
        continue_on_error=False,
        verbose=False,
        report_level="none",
        no_reports=True,
        no_detailed_reports=False,
        simple_report=False,
        smart_reporting_config="",
        case_config="",
    )

    assert cmd_run(ns) == 0
    assert Path(captured["config_path"]) == cfg_path
