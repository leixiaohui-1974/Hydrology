"""HydroMind Workflow Product API.

统一产品化工作流入口。所有工作流通过配置驱动，零硬编码。

工作流注册表：
  init              案例初始化（从 wxq-1d 数据自动生成配置+目录）
  model             水文+水动力建模（含流域划分）
  calibrate         逐站率定验证
  improve           精度自提升（多策略×多分辨率自动择优）
  cascade           梯级全自主运行（10阶段编排）
  pipeline          自学习自提升管线（迭代收敛引擎）
  consolidate       知识固化（合约→YAML 持久化，多版本+会话追踪）
  selfdiag          水动力自诊断自修复
  d1d4              D1-D4 全维度精度报告
  knowledge_mine    模型知识挖掘（原始资产→YAML 知识层）
  state_est         D4 状态估计 EKF（水位校正+精度评价）
  assimilate        多方法数据同化比选（EKF/EnKF/PF/3DVar）
  deep_record       深度资产记录（一次扫描全部数据永久写入YAML）
  ensemble_forecast 嵌套集合预报（长中短 × 多模型 × 不确定性量化 × 可靠性评价）
  dl_transfer       迁移学习（多站预训练 → 新流域微调/零样本，跨流域推广）
  dl_autolearn      DL 自学习闭环（诊断→弱点识别→超参搜索→择优→固化）

使用方式：
  # Python API
  from workflows import WORKFLOW_REGISTRY, run_workflow
  run_workflow("pipeline", case_id="my_case", target_nse=0.85)

  # CLI
  python3 -m workflows.run_self_improving_pipeline --case-id my_case

  # Smart 选流与跑后报告（配置见 configs/workflow_smart_reporting.yaml）
  python3 -m workflows.run_workflow_smart_zh meta   # Agent：打印 CLI 契约 JSON
  python3 -m workflows.run_workflow_smart_zh plan --case-id my_case --json-summary
  python3 -m workflows.run_workflow_smart_zh run --case-id my_case --json-summary
  python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id my_case
"""
from __future__ import annotations

from typing import Any, Callable
from pathlib import Path
import json
import logging
import os
import subprocess
import sys

from workflows.outcome_contract import generate_and_write_outcome
from workflows._reporting import emit_workflow_report, write_report_emit_error_sidecar

_LOG = logging.getLogger(__name__)

WORKFLOW_REGISTRY: dict[str, dict[str, Any]] = {
    "init": {
        "module": "workflows.run_case_init",
        "entry": "run_init",
        "description": "案例初始化（从 wxq-1d 数据自动生成配置+目录）",
        "required_args": ["case_id"],
    },
    "model": {
        "module": "workflows.run_full_modeling",
        "entry": "run_pipeline",
        "description": "水文+水动力建模（含流域划分）",
        "required_args": ["case_id"],
    },
    "calibrate": {
        "module": "workflows.run_calibration_report",
        "entry": "run_report",
        "description": "逐站率定验证",
        "required_args": ["case_id"],
    },
    "improve": {
        "module": "workflows.run_precision_improvement",
        "entry": "run_precision_improvement",
        "description": "精度自提升（多策略×多分辨率自动择优）",
        "required_args": ["case_id"],
    },
    "cascade": {
        "module": "workflows.run_autonomous_cascade",
        "entry": "run_autonomous",
        "description": "梯级全自主运行（10阶段编排）",
        "required_args": ["case_id"],
    },
    "pipeline": {
        "module": "workflows.run_self_improving_pipeline",
        "entry": "run_pipeline",
        "description": "自学习自提升管线（迭代收敛引擎）",
        "required_args": ["case_id"],
    },
    "consolidate": {
        "module": "workflows.run_knowledge_consolidate",
        "entry": "consolidate",
        "description": "知识固化（合约→YAML 持久化，多版本+会话追踪）",
        "required_args": ["case_id"],
    },
    "selfdiag": {
        "module": "workflows.run_hydraulic_selfdiag",
        "entry": "selfdiag",
        "description": "水动力自诊断自修复（边界/水位/收敛/几何自动检测+修复）",
        "required_args": ["case_id"],
    },
    "d1d4": {
        "module": "workflows.run_d1d4_report",
        "entry": "generate_report",
        "description": "D1-D4 全维度精度分析报告",
        "required_args": ["case_id"],
    },
    "business_run_digest": {
        "module": "workflows.generate_business_run_digest",
        "entry": "run_business_run_digest",
        "description": "业务向运行结果汇编（hydromind 六类契约+拓扑样本+运行期对象+工作流与精度摘录）",
        "required_args": ["case_id"],
    },
    "object_topology_report": {
        "module": "workflows.generate_object_topology_report",
        "entry": "run_object_topology_report",
        "description": "刷新标准水对象拓扑样本与 combined_object_topology_report（contract_adapters）",
        "required_args": ["case_id"],
    },
    "autonomy_assess": {
        "module": "workflows.run_autonomy_assessment",
        "entry": "run_autonomy_assessment",
        "description": "端到端自主运行能力评估与闭环建议",
        "required_args": ["case_id"],
    },
    "autonomy_autorun": {
        "module": "workflows.run_autonomy_autorun",
        "entry": "run_autonomy_autorun",
        "description": "端到端自治闭环自动执行（评估→动作→再评估）",
        "required_args": ["case_id"],
    },
    "knowledge_mine": {
        "module": "workflows.run_knowledge_miner",
        "entry": "mine_case",
        "description": "模型知识挖掘（原始资产→YAML 知识层）",
        "required_args": ["case_id"],
    },
    # 与 Agent 表 / E2E 基线中的 workflow_key 对齐（同 knowledge_mine 实现）
    "wxq_mine": {
        "module": "workflows.run_knowledge_miner",
        "entry": "mine_case",
        "description": "WXQ 模型知识挖掘（knowledge_mine 别名，供 MCP/E2E 主键一致）",
        "required_args": ["case_id"],
        "alias_of": "knowledge_mine",
    },
    "state_est": {
        "module": "workflows.run_state_estimation",
        "entry": "run_state_estimation",
        "description": "D4 状态估计 EKF（水位校正+精度评价）",
        "required_args": ["case_id"],
    },
    "assimilate": {
        "module": "workflows.run_data_assimilation",
        "entry": "run_data_assimilation",
        "description": "多方法数据同化比选（EKF/EnKF/PF/3DVar × 水文/水动力/耦合）",
        "required_args": ["case_id"],
    },
    "deep_record": {
        "module": "workflows.run_deep_asset_recorder",
        "entry": "record_assets",
        "description": "深度资产记录（一次扫描全部数据永久写入YAML）",
        "required_args": ["case_id"],
    },
    "source_sync": {
        "module": "workflows.run_source_sync",
        "entry": "run_source_sync",
        "description": "源注册与共享 Wiki 投影（raw source → contracts → wiki）",
        "required_args": ["case_id"],
    },
    "wxq_sync": {
        "module": "workflows.run_source_sync",
        "entry": "run_wxq_sync",
        "description": "WXQ 源注册与共享 Wiki 投影兼容键（等价 source_sync）",
        "required_args": ["case_id"],
        "alias_of": "source_sync",
    },
    "registry": {
        "module": "workflows.run_knowledge_registry",
        "entry": "build_registry",
        "description": "知识注册表（资产→脚本→结果→精度 全链路索引+去重保护）",
        "required_args": ["case_id"],
    },
    "hyd_cal": {
        "module": "workflows.run_hydraulic_calibration",
        "entry": "calibrate_and_validate",
        "description": "水力学历史率定验证（水库水量平衡 × 逐站自提升）",
        "required_args": ["case_id"],
    },
    "hyd_report": {
        "module": "workflows.run_hydraulic_report",
        "entry": "generate_report",
        "description": "D2 水力学精度评价报告（MD + JSON，含建模思路）",
        "required_args": ["case_id"],
    },
    "hydro_report": {
        "module": "workflows.run_hydrology_report",
        "entry": "generate_report",
        "description": "D1 水文精度评价报告（多源择优 MD + 知识固化）",
        "required_args": ["case_id"],
    },
    "coupled": {
        "module": "workflows.run_coupled_hydro_hydraulic",
        "entry": "run_coupled",
        "description": "水文→水力学耦合（D1 出流驱动 D2 水位模拟）",
        "required_args": ["case_id"],
    },
    "data_audit": {
        "module": "workflows.run_data_quality_audit",
        "entry": "run_audit",
        "description": "数据质量审计（完整性/合理性/一致性/负值/缺口诊断）",
        "required_args": ["case_id"],
    },
    "dl_forecast": {
        "module": "workflows.run_dl_forecast",
        "entry": "run_dl_forecast",
        "description": "DL 时序预测（LSTM/Transformer/TimesFM 多模型自动比选）",
        "required_args": ["case_id"],
    },
    "section_analysis": {
        "module": "workflows.run_section_analysis",
        "entry": "run_analysis",
        "description": "断面分析产品（多源解析→水力曲线→5维质量评估→知识固化）",
        "required_args": ["case_id"],
    },
    "ensemble_forecast": {
        "module": "workflows.run_ensemble_forecast",
        "entry": "run_ensemble_forecast",
        "description": "嵌套集合预报（长中短 × 多模型 × 不确定性量化 × 可靠性评价）",
        "required_args": ["case_id"],
    },
    "dl_transfer": {
        "module": "workflows.run_dl_transfer",
        "entry": "run_dl_transfer",
        "description": "迁移学习（多站预训练 → 新流域微调/零样本，跨流域推广）",
        "required_args": ["case_id"],
    },
    "dl_autolearn": {
        "module": "workflows.run_dl_autolearn",
        "entry": "run_dl_autolearn",
        "description": "DL 自学习闭环（诊断→弱点识别→超参搜索→择优→固化）",
        "required_args": ["case_id"],
    },
    "knowledge_split": {
        "module": "workflows.external.run_knowledge_split",
        "entry": "_run_external_script",
        "description": "知识分层迁移（单文件 YAML 拆分为知识目录）",
        "required_args": ["case_id"],
        "external_script": "Hydrology/workflows/run_knowledge_split.py",
        "external_args_template": ["--case-id", "{case_id}"],
        "external_timeout_sec": 600,
    },
    "source_to_delineation": {
        "module": "workflows.external.run_source_to_delineation",
        "entry": "_run_external_script",
        "description": "端到端地形链路（源发现→数据包→流域划分）",
        "required_args": ["case_id"],
        "external_script": "Hydrology/workflows/run_source_to_delineation.py",
        "external_args_template": ["--case-id", "{case_id}"],
        "external_timeout_sec": 900,
    },
    "hyd_sim": {
        # 实际执行走 external_script 子进程；与其它 external 条目一致占位 module/entry
        "module": "workflows.external.run_hydraulic_simulation",
        "entry": "_run_external_script",
        "description": "水力学梯级联合模拟（回溯/级联/场景）",
        "required_args": ["case_id"],
        "external_script": "Hydrology/workflows/run_hydraulic_simulation.py",
        "external_args_template": [
            "--case-id",
            "{case_id}",
            "--mode",
            "replay",
            "--parameter-governance-json",
            "{parameter_governance_json}",
        ],
        "external_contract_files": {"parameter_governance_json": "parameter_governance.latest.json"},
        "external_timeout_sec": 900,
    },

    "case01_local_ext": {
        "module": "workflows.external.run_case01_local",
        "entry": "_run_external_script",
        "description": "pipedream case01 本地运行",
        "required_args": ["case_id"],
        "external_script": "pipedream-hydrology-integration-lab/run_case01_local.py",
        "external_args_template": [],
        "external_timeout_sec": 600,
    },
    "strict_revalidation_ext": {
        "module": "workflows.external.run_strict_revalidation",
        "entry": "_run_external_script",
        "description": "E2E 严格复核验证",
        "required_args": ["case_id"],
        "external_script": "E2EControl/scripts/run_strict_revalidation.py",
        "external_args_template": [],
        "external_timeout_sec": 300,
    },
    "pipedream_report_ext": {
        "module": "workflows.external.run_report",
        "entry": "_run_external_script",
        "description": "pipedream 报告生成",
        "required_args": ["case_id"],
        "external_script": "pipedream-hydrology-integration-lab/run_report.py",
        "external_args_template": ["--case", "{case_id}", "--type", "wnal"],
        "external_timeout_sec": 300,
    },
    "hil_acceptance_test_ext": {
        "module": "workflows.external.run_hil_acceptance_test",
        "entry": "_run_external_script",
        "description": "HIL 验收测试演练",
        "required_args": ["case_id"],
        "external_script": "HIL/examples/run_acceptance_test.py",
        "external_args_template": ["IVCU", "IVCU-{case_id}"],
        "external_timeout_sec": 180,
    },
    # legacy hydro_coupling 脚本已不在仓内；保留兼容键并由通用 Hydrology 耦合工作流承接。
    # 其余 run_daduhe_*.py 已从产品注册表移除，仅作为 legacy/ 历史脚本保留。
    "legacy_hydro_coupling_ext": {
        "module": "workflows.run_coupled_hydro_hydraulic",
        "entry": "run_coupled",
        "description": "legacy 水文→水力耦合通用兼容键（等价 coupled）",
        "required_args": ["case_id"],
        "expose_in_list": False,
        "alias_of": "coupled",
    },
    "wnal_evaluation_ext": {
        "module": "workflows.external.run_wnal_evaluation",
        "entry": "_run_external_script",
        "description": "五案例 WNAL 综合评价（pipedream）",
        "required_args": ["case_id"],
        "external_script": "pipedream-hydrology-integration-lab/run_wnal_evaluation.py",
        "external_args_template": [],
        "external_timeout_sec": 180,
    },
    "mrc_rehearsal_ext": {
        "module": "workflows.external.run_mrc_rehearsal",
        "entry": "_run_external_script",
        "description": "MRC 四态机演练（pipedream）",
        "required_args": ["case_id"],
        "external_script": "pipedream-hydrology-integration-lab/run_mrc_rehearsal.py",
        "external_args_template": [],
        "external_timeout_sec": 180,
    },
}


def _extract_external_result_metadata(stdout: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "QUALITY_GATE_PASSED":
            metadata["quality_gate_passed"] = value.strip().lower() == "true"
        elif key == "QUALITY_STATUS":
            metadata["quality_status"] = value.strip()
        elif key == "QUALITY_REASON":
            metadata["quality_reason"] = value.strip()
        elif key == "STRICT_REVALIDATION_OUTPUT":
            metadata["quality_report_path"] = value.strip()
    if metadata.get("quality_gate_passed") is False:
        metadata["outcome_status"] = "quality_failed"
    return metadata


def _workflow_visible_in_list(spec: dict[str, Any]) -> bool:
    return bool(spec.get("expose_in_list", True))


def _run_external_script(spec: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    script_rel = spec.get("external_script")
    if not script_rel:
        raise ValueError("external_script is required for external workflow")
    script_path = workspace_root / script_rel
    if not script_path.exists():
        raise FileNotFoundError(f"external script not found: {script_path}")

    args_template = spec.get("external_args_template", [])
    case_id = kwargs.get("case_id", "")
    env_overrides = {
        k.removeprefix("_env_"): str(v)
        for k, v in list(kwargs.items())
        if isinstance(k, str) and k.startswith("_env_")
    }
    format_vars = {
        k: v for k, v in kwargs.items()
        if isinstance(k, str) and not k.startswith("_")
    }
    format_vars.setdefault("case_id", case_id)
    # 将 cases/<case_id>/contracts 下约定文件名注入模板占位符（如 hyd_sim 的 parameter_governance_json）
    case_slug = str(case_id or "").strip()
    if case_slug:
        contracts_dir = workspace_root / "cases" / case_slug / "contracts"
        for fmt_key, fname in (spec.get("external_contract_files") or {}).items():
            if fmt_key in format_vars and format_vars[fmt_key]:
                continue
            cand = contracts_dir / str(fname)
            if cand.is_file():
                format_vars[fmt_key] = str(cand.resolve())
    cmd = [sys.executable, str(script_path)]
    for token in args_template:
        if isinstance(token, str):
            try:
                cmd.append(token.format(**format_vars))
            except KeyError as exc:
                missing = str(exc).strip("'\"")
                raise FileNotFoundError(
                    f"external workflow 模板缺少变量 {missing!r}，脚本 {script_rel}，case_id={case_slug!r}；"
                    f"请检查 contracts 是否已生成（如 parameter_governance.latest.json）或通过 kwargs 传入。"
                ) from exc
        else:
            cmd.append(str(token))

    timeout_sec = int(kwargs.pop("_external_timeout_sec", spec.get("external_timeout_sec", 900)))
    env = dict(os.environ)
    env.update(env_overrides)
    # pipedream 脚本依赖 lab 根目录上的兄弟包（如 pipedream_solver、run_ekf_mpc.py）
    pipedream_root = workspace_root / "pipedream-hydrology-integration-lab"
    if (
        pipedream_root.exists()
        and script_path.is_file()
        and pipedream_root in script_path.resolve().parents
    ):
        run_cwd = str(pipedream_root)
    else:
        run_cwd = str(workspace_root)
    proc = subprocess.run(
        cmd,
        cwd=run_cwd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=env,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"external workflow failed ({proc.returncode}): {err[:1200]}")

    result = {
        "kind": "external_script",
        "script": str(script_path),
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[:4000],
        "stderr": (proc.stderr or "")[:4000],
        "execution_status": "completed",
    }
    result.update(_extract_external_result_metadata(proc.stdout or ""))

    # 兼容旧版 strict_revalidation 输出：若 stdout 未给出质量字段，则从 summary 文件回填。
    if script_path.name == "run_strict_revalidation.py" and "quality_gate_passed" not in result:
        report_hint = str(
            result.get("quality_report_path")
            or "reports/acceptance/strict_revalidation_summary.json"
        ).strip()
        report_path = Path(report_hint)
        if not report_path.is_absolute():
            report_path = workspace_root / report_path
        if report_path.exists():
            try:
                summary = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                summary = {}
            if isinstance(summary, dict):
                modules = summary.get("modules", {})
                failed_tests = 0
                if isinstance(modules, dict):
                    for module in modules.values():
                        if isinstance(module, dict):
                            failed_tests += int(module.get("failed_tests", 0) or 0)
                quality_gate = summary.get("quality_gate", {})
                quality_passed = None
                quality_status = ""
                quality_reason = ""
                if isinstance(quality_gate, dict):
                    quality_passed = quality_gate.get("passed")
                    quality_status = str(quality_gate.get("status", "") or "")
                    quality_reason = str(quality_gate.get("reason", "") or "")
                if quality_passed is None:
                    quality_passed = summary.get("quality_gate_passed")
                if quality_passed is None:
                    quality_passed = failed_tests == 0
                if not quality_status:
                    quality_status = str(summary.get("quality_status", "") or "")
                if not quality_status:
                    quality_status = "passed" if bool(quality_passed) else "failed"
                if not quality_reason:
                    quality_reason = str(summary.get("quality_reason", "") or "")
                if not quality_reason:
                    quality_reason = (
                        "all strict revalidation checks passed"
                        if bool(quality_passed)
                        else f"strict revalidation failed_tests={failed_tests}"
                    )
                result["quality_gate_passed"] = bool(quality_passed)
                result["quality_status"] = quality_status
                result["quality_reason"] = quality_reason
                if report_path.is_absolute():
                    try:
                        result["quality_report_path"] = str(report_path.relative_to(workspace_root))
                    except Exception:
                        result["quality_report_path"] = str(report_path)
                else:
                    result["quality_report_path"] = str(report_path)

    if result.get("quality_gate_passed") is False:
        result["outcome_status"] = "quality_failed"
    else:
        result.setdefault("outcome_status", "completed")
    return result


def run_workflow(name: str, **kwargs: Any) -> Any:
    """通过注册表名动态调用工作流。"""
    import importlib
    if name not in WORKFLOW_REGISTRY:
        raise ValueError(
            f"未知工作流 '{name}'。"
            f"中文目录与自动选流: python3 -m workflows.run_workflow_smart_zh plan --case-id <案例ID>；"
            f"端到端说明: python3 -m workflows.run_workflow_smart_zh legend。"
            f" 注册表键: {sorted(WORKFLOW_REGISTRY.keys())}"
        )
    case_id = str(kwargs.get("case_id", "unknown"))
    execution_profile = str(kwargs.pop("_execution_profile", "default"))
    spec = WORKFLOW_REGISTRY[name]
    try:
        if "external_script" in spec:
            result = _run_external_script(spec, **kwargs)
        else:
            mod = importlib.import_module(spec["module"])
            fn = getattr(mod, spec["entry"])
            result = fn(**kwargs)
        outcome_status = "completed"
        if isinstance(result, dict):
            raw_outcome_status = result.get("outcome_status")
            if raw_outcome_status is None:
                raw_status = str(result.get("status") or "").strip().lower()
                if raw_status == "completed" or raw_status in {"partial", "degraded", "error", "failed", "quality_failed", "no_data", "insufficient_data", "skipped"}:
                    raw_outcome_status = raw_status
                elif raw_status.startswith("skipped"):
                    raw_outcome_status = "skipped"
                elif raw_status in {"blocked", "failed_convergence"}:
                    raw_outcome_status = "partial"
            outcome_status = str(raw_outcome_status or outcome_status).strip().lower() or "completed"
            if result.get("quality_gate_passed") is False and outcome_status == "completed":
                outcome_status = "quality_failed"
        try:
            contract = generate_and_write_outcome(
                workflow=name,
                case_id=case_id,
                result=result,
                status=outcome_status,
                execution_profile=execution_profile,
            )
            try:
                emit_workflow_report(
                    case_id=case_id,
                    workflow_key=name,
                    outcome_contract=contract,
                )
            except Exception as emit_exc:
                _LOG.warning(
                    "emit_workflow_report failed workflow=%s case_id=%s",
                    name,
                    case_id,
                    exc_info=True,
                )
                if isinstance(result, dict):
                    result["report_emit_error"] = str(emit_exc)[:500]
                else:
                    try:
                        write_report_emit_error_sidecar(
                            case_id=case_id,
                            workflow_key=name,
                            error_message=str(emit_exc),
                            exc_type=type(emit_exc).__name__,
                        )
                    except Exception:
                        pass
        except Exception:
            # outcome 生成失败不应中断主工作流结果
            pass
        return result
    except Exception as exc:
        try:
            contract = generate_and_write_outcome(
                workflow=name,
                case_id=case_id,
                result={"error": str(exc)},
                status="failed",
                execution_profile=execution_profile,
            )
            try:
                emit_workflow_report(
                    case_id=case_id,
                    workflow_key=name,
                    outcome_contract=contract,
                )
            except Exception as emit_exc:
                _LOG.warning(
                    "emit_workflow_report failed after workflow error workflow=%s case_id=%s",
                    name,
                    case_id,
                    exc_info=True,
                )
                try:
                    write_report_emit_error_sidecar(
                        case_id=case_id,
                        workflow_key=name,
                        error_message=str(emit_exc),
                        exc_type=type(emit_exc).__name__,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        raise


def list_workflows(include_hidden: bool = False) -> list[dict[str, str]]:
    """返回工作流摘要；默认隐藏 legacy case-specific 暴露项。"""
    return [
        {"name": k, "description": v["description"], "args": v["required_args"]}
        for k, v in WORKFLOW_REGISTRY.items()
        if include_hidden or _workflow_visible_in_list(v)
    ]
