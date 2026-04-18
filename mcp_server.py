"""HydroMind MCP Server for Cursor.

将 HydroMind（水智大模型）的产品化工作流暴露为 MCP 工具，供 Cursor/Claude/Codex 等统一调用。
默认使用 stdio 传输，便于在 Cursor 中本地直连。
"""
from __future__ import annotations

import os
import sys
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HYDROLOGY_ROOT = Path(__file__).resolve().parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HYDROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except Exception:
    FastMCP = None  # type: ignore[assignment]
    _HAS_MCP = False

import yaml
from hydro_model.hos_standard import (
    VendorAdapterRegistry,
    build_workflow_compliance_report,
    build_workflow_contract,
    sanitize_for_json,
    validate_workflow_contract,
)
from workflows import WORKFLOW_REGISTRY, list_workflows, run_workflow


if _HAS_MCP and FastMCP is not None:
    mcp = FastMCP("HydroMind")
else:
    mcp = None


def _tool(func):
    if _HAS_MCP and mcp is not None:
        return mcp.tool()(func)
    return func


def _safe_case_root(case_id: str) -> Path:
    case_id = (case_id or "").strip()
    if not case_id:
        raise ValueError("case_id 不能为空")
    if "/" in case_id or ".." in case_id:
        raise ValueError("case_id 非法")
    return HYDROLOGY_ROOT / "cases" / case_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_explicit_case_id(case_id: str | None = None) -> str | None:
    explicit = str(case_id or "").strip()
    if explicit:
        return explicit
    env_case_id = str(os.environ.get("HYDROMIND_DEFAULT_CASE_ID", "")).strip()
    return env_case_id or None


def _vendor_registry() -> VendorAdapterRegistry:
    return VendorAdapterRegistry(HYDROLOGY_ROOT / "configs" / "vendor_adapters.yaml")


def _fast_profile_params(workflow: str) -> dict[str, Any]:
    """E2E 快速验证参数模板（减少长任务超时）。"""
    exact_mapping: dict[str, dict[str, Any]] = {
        "dl_transfer": {"mode": "pretrain", "station_ids": ["s1"], "epochs": 1},
        "dl_forecast": {
            "model_types": ["lstm"],
            "station_ids": ["s1"],
            "epochs": 1,
            "seq_len": 24,
            "horizon": 6,
        },
        "dl_autolearn": {
            "max_rounds": 1,
            "trials_per_weak": 1,
            "station_ids": ["s1"],
            "target_vars": ["H_up"],
            "model_types": ["lstm"],
        },
        "ensemble_forecast": {
            "horizons": ["short"],
            "station_ids": ["s1"],
            "epochs": 1,
        },
        "hyd_cal": {"target_nse": 0.70, "generate_report": False},
        "improve": {"threshold": 0.0, "max_rounds": 1},
        "knowledge_split": {"_external_timeout_sec": 180},
        "source_to_delineation": {"_external_timeout_sec": 300},
        "hyd_sim": {"_external_timeout_sec": 300},
        "strict_revalidation_ext": {
            "_external_timeout_sec": 600,
            "_env_HYDROMIND_FAST_VALIDATION": "1",
            "_env_HYDROMIND_STRICT_REVAL_SCENARIOS": "12",
            "_env_HYDROMIND_STRICT_REVAL_POOL_MULTIPLIER": "3",
            "_env_HYDROMIND_STRICT_REVAL_MODULES": "physics",
        },
        "wnal_evaluation_ext": {"_external_timeout_sec": 180},
        "mrc_rehearsal_ext": {"_external_timeout_sec": 180},
        "case01_local_ext": {"_external_timeout_sec": 180},
        "pipedream_report_ext": {"_external_timeout_sec": 120},
        "hil_acceptance_test_ext": {"_external_timeout_sec": 120},
        "autonomy_autorun": {"execution_profile": "fast_validation", "max_rounds": 2},
    }
    if workflow in exact_mapping:
        return exact_mapping[workflow]

    suffix_mapping: list[tuple[str, dict[str, Any]]] = [
        ("_full_pipeline_ext", {"_external_timeout_sec": 240}),
        ("_pipedream_ext", {"_external_timeout_sec": 240}),
        ("_hydro_coupling_ext", {"_external_timeout_sec": 240}),
        (
            "_historical_validation_ext",
            {
                "_external_timeout_sec": 120,
                "_env_HYDROMIND_FAST_VALIDATION": "1",
            },
        ),
        (
            "_real_validation_ext",
            {
                "_external_timeout_sec": 120,
                "_env_HYDROMIND_FAST_VALIDATION": "1",
            },
        ),
        (
            "_ekf_mpc_ext",
            {
                "_external_timeout_sec": 120,
                "_env_HYDROMIND_FAST_VALIDATION": "1",
            },
        ),
    ]
    for suffix, params in suffix_mapping:
        if workflow.endswith(suffix):
            return params
    return {}


@_tool
def hm_list_workflows() -> dict[str, Any]:
    """列出 HydroMind 可调用工作流。"""
    workflows = []
    for item in list_workflows():
        wf_name = item["name"]
        contract = build_workflow_contract(wf_name, WORKFLOW_REGISTRY[wf_name])
        errors = validate_workflow_contract(contract)
        workflows.append(
            {
                **item,
                "hos_contract_valid": len(errors) == 0,
                "hos_contract_errors": errors,
            }
        )
    return {"count": len(workflows), "workflows": workflows}


@_tool
def hm_list_agents() -> dict[str, Any]:
    """列出水智工坊 Agent 注册表（20 Agent）。"""
    registry_path = HYDROLOGY_ROOT / "configs" / "agent_registry.yaml"
    if not registry_path.exists():
        return {"error": f"未找到注册表: {registry_path}"}
    with registry_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents", {})
    items = []
    for key, info in agents.items():
        items.append(
            {
                "id": key,
                "name": info.get("name", key),
                "number": info.get("number"),
                "subtitle": info.get("subtitle", ""),
                "projects": info.get("projects", []),
            }
        )
    items.sort(key=lambda x: (x.get("number") or 999, x["id"]))
    return {"count": len(items), "agents": items}


@_tool
def hm_run_workflow(
    workflow: str,
    case_id: str,
    params: dict[str, Any] | None = None,
    execution_profile: str = "default",
) -> dict[str, Any]:
    """运行产品化工作流。

    Args:
        workflow: 工作流名（如 section_analysis / pipeline / hyd_cal）
        case_id: 案例 ID（如 zhongxian）
        params: 额外参数（可选）
    """
    if workflow not in WORKFLOW_REGISTRY:
        return {
            "ok": False,
            "error": f"未知 workflow: {workflow}",
            "available": sorted(WORKFLOW_REGISTRY.keys()),
        }
    args: dict[str, Any] = {"case_id": case_id}
    args["_execution_profile"] = execution_profile
    if execution_profile == "fast_validation":
        args.update(_fast_profile_params(workflow))
    if params:
        # 用户显式参数优先
        args.update(params)

    try:
        contract = build_workflow_contract(workflow, WORKFLOW_REGISTRY[workflow])
        contract_errors = validate_workflow_contract(contract)
        if contract_errors:
            return {
                "ok": False,
                "workflow": workflow,
                "case_id": case_id,
                "error": "workflow contract validation failed",
                "contract_errors": contract_errors,
            }

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            result = run_workflow(workflow, **args)

        return {
            "ok": True,
            "workflow": workflow,
            "case_id": case_id,
            "result": sanitize_for_json(result),
            "_hos": {
                "contract_type": "workflow",
                "workflow_contract_version": contract.get("hos_version"),
                "unit_system": contract.get("inputs", {}).get("unit_system", "SI"),
                "_auto_generated": True,
                "executed_at": _utc_now(),
                "execution_profile": execution_profile,
            },
            "runtime_capture": {
                "stdout": stdout_buf.getvalue()[:4000],
                "stderr": stderr_buf.getvalue()[:4000],
                "truncated": len(stdout_buf.getvalue()) > 4000 or len(stderr_buf.getvalue()) > 4000,
            },
        }
    except Exception as exc:
        return {"ok": False, "workflow": workflow, "case_id": case_id, "error": str(exc)}


@_tool
def hm_list_contracts(case_id: str) -> dict[str, Any]:
    """列出案例 contracts 目录下的产出文件。"""
    contracts_dir = _safe_case_root(case_id) / "contracts"
    if not contracts_dir.exists():
        return {"ok": False, "error": f"目录不存在: {contracts_dir}"}
    files = sorted([p.name for p in contracts_dir.iterdir() if p.is_file()])
    return {"ok": True, "case_id": case_id, "count": len(files), "files": files}


@_tool
def hm_read_contract(case_id: str, filename: str, max_chars: int = 12000) -> dict[str, Any]:
    """读取案例合同化产物（报告/JSON/YAML）。"""
    if "/" in filename or ".." in filename:
        return {"ok": False, "error": "filename 非法"}
    contracts_dir = _safe_case_root(case_id) / "contracts"
    target = contracts_dir / filename
    if not target.exists():
        return {"ok": False, "error": f"文件不存在: {target}"}
    text = target.read_text(encoding="utf-8", errors="ignore")
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    return {"ok": True, "path": str(target), "content": text}


@_tool
def hm_health(case_id: str | None = None) -> dict[str, Any]:
    """健康检查：确认关键目录和配置可用。"""
    explicit_case_id = _resolve_explicit_case_id(case_id)
    payload = {
        "ok": True,
        "repo_root": str(REPO_ROOT),
        "hydrology_root": str(HYDROLOGY_ROOT),
        "case_id": explicit_case_id,
        "workflow_count": len(WORKFLOW_REGISTRY),
        "case_checks_skipped": explicit_case_id is None,
    }
    if explicit_case_id is not None:
        cfg_path = HYDROLOGY_ROOT / "configs" / f"{explicit_case_id}.yaml"
        case_root = HYDROLOGY_ROOT / "cases" / explicit_case_id
        payload["config_exists"] = cfg_path.exists()
        payload["case_root_exists"] = case_root.exists()
    return payload


@_tool
def hm_hos_compliance_report(save_to_contracts: bool = True, case_id: str | None = None) -> dict[str, Any]:
    """生成并返回 HOS 工作流合规报告。"""
    explicit_case_id = _resolve_explicit_case_id(case_id)
    report = build_workflow_compliance_report(WORKFLOW_REGISTRY)
    out_path: str | None = None
    warning: str | None = None
    if save_to_contracts and explicit_case_id is not None:
        contracts = _safe_case_root(explicit_case_id) / "contracts"
        contracts.mkdir(parents=True, exist_ok=True)
        out_file = contracts / "hos_workflow_compliance_report.json"
        out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        out_path = str(out_file)
    elif save_to_contracts:
        warning = "未显式提供 case_id，已跳过按案例落盘。可传入 case_id 或设置 HYDROMIND_DEFAULT_CASE_ID。"
    return {
        "ok": True,
        "report": report,
        "saved_path": out_path,
        "case_id": explicit_case_id,
        "warning": warning,
    }


@_tool
def hm_hos_register_vendor_adapter(manifest: dict[str, Any]) -> dict[str, Any]:
    """注册第三方模型/工作流厂商适配器到产品注册表。"""
    try:
        saved = _vendor_registry().register_vendor(manifest)
        return {"ok": True, "vendor": saved}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@_tool
def hm_hos_list_vendor_adapters() -> dict[str, Any]:
    """列出已接入的第三方厂商适配器。"""
    vendors = _vendor_registry().list_vendors()
    return {"ok": True, "count": len(vendors), "vendors": vendors}


if __name__ == "__main__":
    if not _HAS_MCP or mcp is None:
        print("错误: 缺少 mcp 依赖。请先执行: python3 -m pip install mcp")
        sys.exit(1)
    transport = os.environ.get("HYDROMIND_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run()
