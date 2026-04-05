#!/usr/bin/env python3
"""
HydroDesk Phase 1 — Agent Loop 网关（轻量，stdio NDJSON）。

与 Phase 1 路线图「方案 B」一致：不依赖 claw-code 构建链，供 Tauri 侧将来以子进程 + 管道
双向通讯；工具实现与现有 shell 按钮同源（脚本路径配置在注册表内，无案例 if/elif）。

协议：每行一条 JSON（UTF-8），响应同样一行 JSON flush 到 stdout。

  {"op":"ping"}
  {"op":"list_tools"}   # 不筛选（全量工具）
  {"op":"list_tools","case_id":"daduhe"}  # 按 manifest.workflow_targets 过滤（Layer 3 沙箱）
  {"op":"invoke_tool","tool":"case_knowledge_lint","case_id":"daduhe"}
  {"op":"invoke_tool","tool":"delivery_docs_pack_dry_run","case_id":"daduhe"}

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

_CASE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# 工具与 manifest.workflow_targets 的交集策略：空列表 = 不依赖 targets，始终可用
TOOL_WORKFLOW_TARGET_TAGS: dict[str, list[str]] = {
    "case_knowledge_lint": [],
    "bootstrap_case_triad_minimal": [],
    # 交付/验收链工具：仅当案例声明了验收或发布类 target 时开放
    "delivery_docs_pack_dry_run": ["acceptance_review", "release_publish"],
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


def _run_argv(ws: Path, argv: list[str], *, timeout: int = 300) -> dict[str, Any]:
    proc = subprocess.run(
        argv,
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "")[-12000:]
    err = (proc.stderr or "")[-8000:]
    return {
        "returncode": proc.returncode,
        "stdout_tail": out,
        "stderr_tail": err,
        "ok": proc.returncode == 0,
    }


def _tool_registry(py: str, ws: Path) -> dict[str, Callable[[str], list[str]]]:
    """tool name -> build argv (case_id already validated)."""

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

    return {
        "case_knowledge_lint": knowledge_lint,
        "bootstrap_case_triad_minimal": bootstrap_triad,
        "delivery_docs_pack_dry_run": delivery_dry,
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
    ]


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
    policy: dict[str, Any] = {
        "case_id": case_id or "",
        "workflow_targets": None,
        "filter_mode": "none",
    }
    if not case_id:
        return _tool_meta(), policy
    try:
        cid = _validate_case_id(case_id)
    except ValueError as e:
        return [], {**policy, "filter_mode": "invalid_case_id", "error": str(e)}
    targets = _load_workflow_targets(ws, cid)
    policy["workflow_targets"] = targets
    policy["filter_mode"] = "manifest_workflow_targets" if targets is not None else "manifest_missing_or_no_key"
    meta = [m for m in _tool_meta() if _tool_allowed_for_targets(m["name"], targets)]
    return meta, policy


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

    if op == "invoke_tool":
        name = (msg.get("tool") or "").strip()
        reg = _tool_registry(py, ws)
        if name not in reg:
            return {"ok": False, "error": "unknown_tool", "tool": name, "known": list(reg)}
        try:
            cid = _validate_case_id(str(msg.get("case_id") or ""))
        except ValueError as e:
            return {"ok": False, "error": "invalid_case_id", "detail": str(e)}
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
        if not Path(argv[1]).is_file():
            return {"ok": False, "error": "script_missing", "path": argv[1]}
        body = _run_argv(ws, argv)
        return {"ok": body.get("ok"), "tool": name, "case_id": cid, "result": body}

    return {"ok": False, "error": "unknown_op", "op": op}


def run_loop() -> None:
    ws = _resolve_workspace()
    py = sys.executable
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _reply({"ok": False, "error": "invalid_json", "detail": str(e)})
            continue
        if not isinstance(msg, dict):
            _reply({"ok": False, "error": "message_not_object"})
            continue
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
        msg = json.loads(raw)
        ws = _resolve_workspace()
        py = sys.executable
        _reply(_handle(msg, ws, py))
        return
    run_loop()


if __name__ == "__main__":
    main()
