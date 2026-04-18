#!/usr/bin/env python3
"""
HydroDesk Phase 1 — Agent Loop 网关（轻量，stdio NDJSON）。

与 Phase 1 路线图「方案 B」一致：不依赖 claw-code 构建链，供 Tauri 侧将来以子进程 + 管道
双向通讯；工具实现与现有 shell 按钮同源（脚本路径配置在注册表内，无案例 if/elif）。

协议：每行一条 JSON（UTF-8），响应同样一行 JSON flush 到 stdout。

  {"op":"ping"}
  {"op":"list_tools"}   # 不筛选（全量工具）
  {"op":"list_tools","case_id":"zhongxian"}  # 按 manifest.workflow_targets 过滤（Layer 3 沙箱）
  {"op":"invoke_tool","tool":"case_knowledge_lint","case_id":"zhongxian"}
  {"op":"invoke_tool","tool":"delivery_docs_pack_dry_run","case_id":"zhongxian"}

环境变量：
  AGENT_LOOP_GATEWAY_WORKSPACE — 可选，覆盖仓库根（默认为本文件上两级目录的父级，即 monorepo root）。

桌面壳（HydroDesk Tauri）：
  - **oneshot**：`agent_loop_gateway_oneshot` → `python3 …/agent_loop_gateway.py --oneshot <json>`，无 shell 拼接。
  - **常驻**：`agent_loop_gateway_session_start` 启动子进程跑本文件主循环；前端经 `agent_loop_gateway_session_send` 逐行写 stdin，stdout NDJSON 经事件 `agent-loop-gateway-line` 推送。应用 `RunEvent::Exit` 时会 `kill/wait` 子进程，避免遗留 Python 网关进程。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

HYDROLOGY_ROOT = WORKSPACE / "Hydrology"
_SCRIPTS = HYDROLOGY_ROOT / "scripts"
_WORKFLOWS = HYDROLOGY_ROOT / "workflows"
AGENT_VISIBLE_WORKFLOWS_CONFIG = HYDROLOGY_ROOT / "configs" / "agent_visible_workflows.yaml"

if str(HYDROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY_ROOT))

from workflows.run_workflow_smart_zh import (  # noqa: E402
    _scoped_cli_result_relpath,
    _standard_smart_artifact_relpaths,
)

_CASE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# 工具与 manifest.workflow_targets 的交集策略：空列表 = 不依赖 targets，始终可用
SMART_TOOL_NAMES = {
    "smart_meta",
    "smart_plan",
    "smart_run",
    "smart_refresh_reports",
    "smart_status",
}

SMART_TOOL_RESULT_SCOPE: dict[str, dict[str, Any]] = {
    "smart_plan": {"command": "plan", "profile": "smart", "dry_run": False},
    "smart_run": {"command": "run", "profile": "smart", "dry_run": False},
    "smart_refresh_reports": {"command": "refresh-reports", "profile": "smart", "dry_run": False},
}

SMART_TOOL_TIMEOUT_SECONDS: dict[str, int] = {
    "smart_run": 1800,
}

TOOLS_WITH_OPTIONAL_CASE_ID = {
    "smart_meta",
}

TOOL_WORKFLOW_TARGET_TAGS: dict[str, list[str]] = {
    "case_knowledge_lint": [],
    "bootstrap_case_triad_minimal": [],
    # 交付/验收链工具：仅当案例声明了验收或发布类 target 时开放
    "delivery_docs_pack_dry_run": ["acceptance_review", "release_publish"],
    "smart_meta": [],
    "smart_plan": [],
    "smart_run": [],
    "smart_refresh_reports": [],
    "smart_status": [],
}

TOOL_VISIBLE_WORKFLOW_KEYS: dict[str, list[str] | None] = {
    "case_knowledge_lint": [],
    "bootstrap_case_triad_minimal": ["init"],
    # 交付文档包仍由 case workflow_targets 决定，本轮不绑定到全局 workflow allowlist。
    "delivery_docs_pack_dry_run": None,
    "smart_meta": None,
    "smart_plan": None,
    "smart_run": None,
    "smart_refresh_reports": None,
    "smart_status": None,
}


def _resolve_workspace() -> Path:
    raw = (os.environ.get("AGENT_LOOP_GATEWAY_WORKSPACE") or "").strip()
    if raw:
        return Path(raw).resolve()
    return WORKSPACE


def _validate_case_id(case_id: str) -> str:
    cid = (case_id or "").strip()
    if not cid or not _CASE_ID_RE.match(cid):
        raise ValueError("case_id 非法或为空（仅允许字母数字、_、-）")
    return cid


def _reply(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tail_text(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-limit:]
    return str(value)[-limit:]


def _run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout_tail": _tail_text(exc.output, limit=12000),
            "stderr_tail": _tail_text(exc.stderr, limit=8000),
            "ok": False,
            "error": "tool_timeout",
            "timeout_seconds": timeout,
            "detail": f"tool timed out after {timeout}s",
        }
    out = _tail_text(proc.stdout, limit=12000)
    err = _tail_text(proc.stderr, limit=8000)
    return {
        "returncode": proc.returncode,
        "stdout_tail": out,
        "stderr_tail": err,
        "ok": proc.returncode == 0,
    }


def _smart_cli_base_argv(py: str) -> list[str]:
    return [py, str(_WORKFLOWS / "run_workflow_smart_zh.py")]


def _smart_cli_restrict_workflow_argv(visible_cfg: dict[str, Any]) -> list[str]:
    allowlist = [str(item).strip() for item in visible_cfg.get("allowlist") or [] if str(item).strip()]
    if not bool(visible_cfg.get("enabled")) or not allowlist:
        return []
    return ["--restrict-workflow-keys", ",".join(allowlist)]


def _smart_cli_result_paths(
    ws: Path,
    case_id: str,
    *,
    command: str,
    profile: str,
    dry_run: bool,
) -> dict[str, Path]:
    arts = _standard_smart_artifact_relpaths(case_id)
    shared_rel = arts["cli_result"]
    scoped_rel = _scoped_cli_result_relpath(
        case_id,
        command=command,
        profile=profile,
        dry_run=dry_run,
    )
    return {
        "shared": ws / shared_rel,
        "scoped": ws / scoped_rel,
    }


def _smart_status_payload(ws: Path, case_id: str) -> dict[str, Any]:
    arts = _standard_smart_artifact_relpaths(case_id)
    resolved = {name: ws / rel for name, rel in arts.items()}
    default_scoped_rel = _scoped_cli_result_relpath(
        case_id,
        command="run",
        profile="smart",
        dry_run=False,
    )
    scoped_path = ws / default_scoped_rel
    shared_path = resolved["cli_result"]
    return {
        "case_id": case_id,
        "artifacts": {
            **arts,
            "default_scoped_cli_result": default_scoped_rel,
        },
        "exists": {
            **{name: path.is_file() for name, path in resolved.items()},
            "default_scoped_cli_result": scoped_path.is_file(),
        },
        "shared_cli_result_path": str(shared_path),
        "shared_cli_result_exists": shared_path.is_file(),
        "scoped_cli_result_path": str(scoped_path),
        "scoped_cli_result_exists": scoped_path.is_file(),
        "cli_result_path": str(shared_path),
        "cli_result_exists": shared_path.is_file(),
        "latest_cli_result": str(shared_path) if shared_path.is_file() else None,
    }


def _tool_registry(py: str, ws: Path, visible_cfg: dict[str, Any] | None = None) -> dict[str, Callable[[str], list[str]]]:
    """tool name -> build argv (case_id already validated unless optional-case tool)."""

    smart_restrict_argv = _smart_cli_restrict_workflow_argv(visible_cfg or {})

    def knowledge_lint(cid: str) -> list[str]:
        return [
            py,
            str(_SCRIPTS / "lint_case_knowledge_links.py"),
            "--case-id",
            cid,
        ]

    def bootstrap_triad(cid: str) -> list[str]:
        return [
            py,
            str(_SCRIPTS / "bootstrap_case_triad_minimal.py"),
            "--apply",
            "--case-id",
            cid,
        ]

    def delivery_dry(cid: str) -> list[str]:
        return [
            py,
            str(_WORKFLOWS / "hydrodesk_e2e_actions.py"),
            "--case-id",
            cid,
            "--action",
            "generate-delivery-docs-pack",
            "--delivery-pack-dry-run",
        ]

    def smart_meta(_cid: str) -> list[str]:
        return [*_smart_cli_base_argv(py), "meta"]

    def smart_plan(cid: str) -> list[str]:
        return [
            *_smart_cli_base_argv(py),
            "plan",
            "--case-id",
            cid,
            *smart_restrict_argv,
            "--json-summary",
            "--print-json-summary",
        ]

    def smart_run(cid: str) -> list[str]:
        return [
            *_smart_cli_base_argv(py),
            "run",
            "--case-id",
            cid,
            "--profile",
            "smart",
            *smart_restrict_argv,
            "--json-summary",
            "--print-json-summary",
        ]

    def smart_refresh_reports(cid: str) -> list[str]:
        return [
            *_smart_cli_base_argv(py),
            "refresh-reports",
            "--case-id",
            cid,
            "--report-level",
            "detailed",
            "--json-summary",
            "--print-json-summary",
        ]

    return {
        "case_knowledge_lint": knowledge_lint,
        "bootstrap_case_triad_minimal": bootstrap_triad,
        "delivery_docs_pack_dry_run": delivery_dry,
        "smart_meta": smart_meta,
        "smart_plan": smart_plan,
        "smart_run": smart_run,
        "smart_refresh_reports": smart_refresh_reports,
    }


def _tool_meta() -> list[dict[str, str]]:
    return [
        {
            "name": "case_knowledge_lint",
            "summary": "运行 lint_case_knowledge_links.py（案例知识壳 Markdown 链接等）",
        },
        {
            "name": "bootstrap_case_triad_minimal",
            "summary": "bootstrap_case_triad_minimal.py --apply（最小 triad 占位）",
        },
        {
            "name": "delivery_docs_pack_dry_run",
            "summary": "hydrodesk_e2e_actions generate-delivery-docs-pack --delivery-pack-dry-run",
        },
        {
            "name": "smart_meta",
            "summary": "读取 smart CLI 契约 JSON，供 Claude Code / Codex / 网关发现稳定入口",
        },
        {
            "name": "smart_plan",
            "summary": "调用 smart CLI 生成中文计划与机器摘要 JSON",
        },
        {
            "name": "smart_run",
            "summary": "调用 smart CLI 以 smart 模式执行端到端建模并输出机器摘要",
        },
        {
            "name": "smart_refresh_reports",
            "summary": "调用 smart CLI 刷新 smart 跑后报告链与机器摘要",
        },
        {
            "name": "smart_status",
            "summary": "读取 smart 计划/执行/机器摘要产物是否存在，便于 Claude Code 查询状态",
        },
    ]


def _normalize_workflow_key(key: str, aliases: dict[str, str]) -> str:
    current = str(key or "").strip()
    seen: set[str] = set()
    while current and current in aliases and current not in seen:
        seen.add(current)
        current = str(aliases[current]).strip()
    return current


def _load_agent_visible_workflows() -> dict[str, Any]:
    fallback = {
        "enabled": False,
        "mode": "disabled",
        "allowlist": [],
        "aliases": {},
        "path": str(AGENT_VISIBLE_WORKFLOWS_CONFIG),
        "source": "missing_config",
    }
    if yaml is None or not AGENT_VISIBLE_WORKFLOWS_CONFIG.is_file():
        return fallback
    try:
        raw = yaml.safe_load(AGENT_VISIBLE_WORKFLOWS_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:
        return {
            **fallback,
            "enabled": True,
            "mode": "allowlist",
            "source": "invalid_config",
        }
    if not isinstance(raw, dict):
        return {
            **fallback,
            "enabled": True,
            "mode": "allowlist",
            "source": "invalid_config",
        }

    defaults = raw.get("defaults") or {}
    aliases_raw = raw.get("aliases") or {}
    aliases = {
        str(alias).strip(): str(target).strip()
        for alias, target in aliases_raw.items()
        if str(alias).strip() and str(target).strip()
    }
    normalized_allowlist: list[str] = []
    for item in raw.get("allowlist") or []:
        normalized = _normalize_workflow_key(str(item).strip(), aliases)
        if normalized and normalized not in normalized_allowlist:
            normalized_allowlist.append(normalized)

    enabled = bool(defaults.get("enabled", True))
    mode = str(defaults.get("mode") or "allowlist").strip() or "allowlist"
    if enabled and not normalized_allowlist:
        return {
            "enabled": True,
            "mode": mode,
            "allowlist": [],
            "aliases": aliases,
            "path": str(AGENT_VISIBLE_WORKFLOWS_CONFIG),
            "source": "empty_allowlist",
        }

    return {
        "enabled": enabled,
        "mode": mode,
        "allowlist": normalized_allowlist,
        "aliases": aliases,
        "path": str(AGENT_VISIBLE_WORKFLOWS_CONFIG),
        "source": "config_file",
    }


def _tool_allowed_by_visible_workflows(tool_name: str, visible_cfg: dict[str, Any]) -> bool:
    if not bool(visible_cfg.get("enabled")):
        return True

    workflow_keys = TOOL_VISIBLE_WORKFLOW_KEYS.get(tool_name)
    allowlist = [str(item).strip() for item in visible_cfg.get("allowlist") or [] if str(item).strip()]
    source = str(visible_cfg.get("source") or "")
    if not allowlist and source in {"invalid_config", "empty_allowlist"}:
        return workflow_keys == []
    if workflow_keys is None:
        return True
    if workflow_keys == []:
        return True

    aliases = visible_cfg.get("aliases") or {}
    visible = {
        _normalize_workflow_key(str(item), aliases)
        for item in allowlist
    }
    required = {
        _normalize_workflow_key(str(item), aliases)
        for item in workflow_keys
    }
    return bool(visible & required)


def _manifest_path(ws: Path, case_id: str) -> Path:
    return ws / "cases" / case_id / "manifest.yaml"


def _load_workflow_targets(ws: Path, case_id: str) -> list[str] | None:
    """
    读取 cases/<case_id>/manifest.yaml 顶层的 workflow_targets。
    返回 None 表示：文件不存在、无法解析 YAML、或缺少该键 —— 网关不对工具做 target 过滤（兼容旧案例）。
    返回 [] 表示键存在且为空列表 —— 带标签工具全部不可用。
    """
    path = _manifest_path(ws, case_id)
    if yaml is None or not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    if "workflow_targets" not in raw:
        return None
    wt = raw.get("workflow_targets")
    if not isinstance(wt, list):
        return None
    out = [str(x).strip() for x in wt if isinstance(x, str) and str(x).strip()]
    return out


def _tool_allowed_for_targets(tool_name: str, workflow_targets: list[str] | None) -> bool:
    required = TOOL_WORKFLOW_TARGET_TAGS.get(tool_name)
    if not required:
        return True
    if workflow_targets is None:
        return True
    return bool(set(required) & set(workflow_targets))


def _filter_tools_for_case(
    ws: Path, case_id: str | None
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    visible_cfg = _load_agent_visible_workflows()
    policy: dict[str, Any] = {
        "case_id": case_id or "",
        "workflow_targets": None,
        "filter_mode": "none",
        "agent_visible_workflows": {
            "enabled": bool(visible_cfg.get("enabled")),
            "mode": str(visible_cfg.get("mode") or "disabled"),
            "allowlist": visible_cfg.get("allowlist") or [],
            "path": str(visible_cfg.get("path") or ""),
            "source": str(visible_cfg.get("source") or ""),
        },
    }
    if not case_id:
        meta = [m for m in _tool_meta() if _tool_allowed_by_visible_workflows(m["name"], visible_cfg)]
        return meta, policy
    try:
        cid = _validate_case_id(case_id)
    except ValueError as e:
        return [], {**policy, "filter_mode": "invalid_case_id", "error": str(e)}
    targets = _load_workflow_targets(ws, cid)
    policy["workflow_targets"] = targets
    policy["filter_mode"] = "manifest_workflow_targets" if targets is not None else "manifest_missing_or_no_key"
    meta = [
        m
        for m in _tool_meta()
        if _tool_allowed_by_visible_workflows(m["name"], visible_cfg)
        and _tool_allowed_for_targets(m["name"], targets)
    ]
    return meta, policy


def _decode_request(raw: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, {"ok": False, "error": "invalid_json", "detail": str(e)}
    if not isinstance(msg, dict):
        return None, {"ok": False, "error": "message_not_object"}
    return msg, None


def _handle(msg: dict[str, Any], ws: Path, py: str) -> dict[str, Any]:
    op = (msg.get("op") or "").strip()
    if op == "ping":
        return {"ok": True, "pong": True, "workspace": str(ws)}

    if op == "list_tools":
        raw_case = msg.get("case_id")
        case_part = str(raw_case).strip() if raw_case is not None else ""
        tools, policy = _filter_tools_for_case(ws, case_part or None)
        if not tools and policy.get("filter_mode") == "invalid_case_id":
            return {"ok": False, "error": "invalid_case_id", "detail": policy.get("error")}
        return {"ok": True, "tools": tools, "policy": policy}

    visible_cfg = _load_agent_visible_workflows()
    reg = _tool_registry(py, ws, visible_cfg)
    if op in reg or op == "smart_status":
        msg = {**msg, "op": "invoke_tool", "tool": op}
        op = "invoke_tool"

    if op == "invoke_tool":
        name = (msg.get("tool") or "").strip()
        if name == "smart_status":
            try:
                cid = _validate_case_id(str(msg.get("case_id") or ""))
            except ValueError as e:
                return {"ok": False, "error": "invalid_case_id", "detail": str(e)}
            if not _tool_allowed_by_visible_workflows(name, visible_cfg):
                return {
                    "ok": False,
                    "error": "tool_not_visible_globally",
                    "tool": name,
                    "case_id": cid,
                    "agent_visible_workflows": {
                        "mode": str(visible_cfg.get("mode") or "disabled"),
                        "allowlist": visible_cfg.get("allowlist") or [],
                    },
                    "required_workflow_keys": TOOL_VISIBLE_WORKFLOW_KEYS.get(name) or [],
                }
            targets = _load_workflow_targets(ws, cid)
            if not _tool_allowed_for_targets(name, targets):
                return {
                    "ok": False,
                    "error": "tool_not_allowed_for_case",
                    "tool": name,
                    "case_id": cid,
                    "workflow_targets": targets,
                    "required_workflow_target_tags": TOOL_WORKFLOW_TARGET_TAGS.get(name, []),
                }
            return {"ok": True, "tool": name, "case_id": cid, "result": _smart_status_payload(ws, cid)}
        if name not in reg:
            return {"ok": False, "error": "unknown_tool", "tool": name, "known": list(reg)}
        raw_case_id = str(msg.get("case_id") or "")
        if name in TOOLS_WITH_OPTIONAL_CASE_ID:
            cid = raw_case_id.strip()
        else:
            try:
                cid = _validate_case_id(raw_case_id)
            except ValueError as e:
                return {"ok": False, "error": "invalid_case_id", "detail": str(e)}
        if not _tool_allowed_by_visible_workflows(name, visible_cfg):
            return {
                "ok": False,
                "error": "tool_not_visible_globally",
                "tool": name,
                "case_id": cid,
                "agent_visible_workflows": {
                    "mode": str(visible_cfg.get("mode") or "disabled"),
                    "allowlist": visible_cfg.get("allowlist") or [],
                },
                "required_workflow_keys": TOOL_VISIBLE_WORKFLOW_KEYS.get(name) or [],
            }
        if name not in TOOLS_WITH_OPTIONAL_CASE_ID:
            targets = _load_workflow_targets(ws, cid)
            if not _tool_allowed_for_targets(name, targets):
                return {
                    "ok": False,
                    "error": "tool_not_allowed_for_case",
                    "tool": name,
                    "case_id": cid,
                    "workflow_targets": targets,
                    "required_workflow_target_tags": TOOL_WORKFLOW_TARGET_TAGS.get(name, []),
                }
        argv = reg[name](cid)
        module_index = argv.index("-m") if "-m" in argv else -1
        if module_index < 0 and len(argv) > 1 and not Path(argv[1]).is_file():
            return {"ok": False, "error": "script_missing", "path": argv[1]}
        timeout = int(SMART_TOOL_TIMEOUT_SECONDS.get(name, 300))
        body = _run_argv(ws, argv, timeout=timeout)
        extra: dict[str, Any] = {}
        if name in SMART_TOOL_NAMES and name != "smart_meta" and cid:
            scope = SMART_TOOL_RESULT_SCOPE.get(name)
            if scope is not None:
                result_paths = _smart_cli_result_paths(
                    ws,
                    cid,
                    command=str(scope["command"]),
                    profile=str(scope["profile"]),
                    dry_run=bool(scope["dry_run"]),
                )
                extra["shared_cli_result_path"] = str(result_paths["shared"])
                extra["shared_cli_result_exists"] = result_paths["shared"].is_file()
                extra["scoped_cli_result_path"] = str(result_paths["scoped"])
                extra["scoped_cli_result_exists"] = result_paths["scoped"].is_file()
                extra["cli_result_path"] = str(result_paths["shared"])
                extra["cli_result_exists"] = result_paths["shared"].is_file()
                extra["latest_cli_result"] = (
                    str(result_paths["shared"]) if result_paths["shared"].is_file() else None
                )
        return {"ok": body.get("ok"), "tool": name, "case_id": cid, "result": body, **extra}

    return {"ok": False, "error": "unknown_op", "op": op}


def run_loop() -> None:
    ws = _resolve_workspace()
    py = sys.executable
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg, err = _decode_request(line)
        if err is not None:
            _reply(err)
            continue
        assert msg is not None
        try:
            out = _handle(msg, ws, py)
        except Exception as e:  # noqa: BLE001 — 网关顶层兜底
            _reply({"ok": False, "error": "internal", "detail": str(e)})
            continue
        _reply(out)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--oneshot":
        # 调试: python3 agent_loop_gateway.py --oneshot <json line>
        raw = sys.argv[2] if len(sys.argv) > 2 else '{"op":"ping"}'
        msg, err = _decode_request(raw)
        if err is not None:
            _reply(err)
            return
        assert msg is not None
        ws = _resolve_workspace()
        py = sys.executable
        try:
            _reply(_handle(msg, ws, py))
        except Exception as e:  # noqa: BLE001 — 网关顶层兜底
            _reply({"ok": False, "error": "internal", "detail": str(e)})
        return
    run_loop()


if __name__ == "__main__":
    main()
