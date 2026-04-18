#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
GATEWAY = WORKSPACE / "Hydrology" / "workflows" / "agent_loop_gateway.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate A-01 runtime happy path proof artifact.")
    parser.add_argument("--case-id", required=True)
    return parser


def proof_paths(case_id: str) -> tuple[Path, Path]:
    base = WORKSPACE / "cases" / case_id / "contracts"
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / "agent_runtime_happy_path.latest.json",
        base / "agent_runtime_happy_path.latest.md",
    )


def run_gateway_happy_path(case_id: str) -> dict:
    proc = subprocess.Popen(
        [sys.executable, str(GATEWAY)],
        cwd=str(WORKSPACE),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    steps: list[dict[str, str]] = []
    recent_trace: list[dict] = []
    recent_stderr: list[str] = []

    try:
        alive = proc.poll() is None
        steps.append(
            {
                "label": "启动 session",
                "status": "passed" if alive else "failed",
                "detail": f"session pid {proc.pid}" if alive else "gateway exited immediately",
            }
        )
        if not alive:
            raise RuntimeError("gateway failed to stay alive")

        assert proc.stdin is not None
        assert proc.stdout is not None

        def send_and_read(payload: dict) -> dict:
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            if not line:
                raise RuntimeError(f"no response for {payload}")
            obj = json.loads(line)
            recent_trace.append(obj)
            return obj

        pong = send_and_read({"op": "ping"})
        pong_ok = pong.get("pong") is True
        steps.append(
            {
                "label": "Ping",
                "status": "passed" if pong_ok else "failed",
                "detail": "收到 pong" if pong_ok else json.dumps(pong, ensure_ascii=False),
            }
        )
        if not pong_ok:
            raise RuntimeError("ping failed")

        tools_reply = send_and_read({"op": "list_tools", "case_id": case_id})
        tools = tools_reply.get("tools") or []
        tools_ok = bool(tools_reply.get("ok")) and len(tools) > 0
        policy = tools_reply.get("policy", {})
        detail = f"tools={len(tools)}"
        if policy.get("filter_mode"):
            detail += f" · policy={policy['filter_mode']}"
        steps.append(
            {
                "label": "List Tools",
                "status": "passed" if tools_ok else "failed",
                "detail": detail if tools_ok else json.dumps(tools_reply, ensure_ascii=False),
            }
        )
        if not tools_ok:
            raise RuntimeError("list_tools failed")
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            stderr_text = (proc.stderr.read() or "").strip() if proc.stderr else ""
            if stderr_text:
                recent_stderr = [line for line in stderr_text.splitlines() if line.strip()][-8:]
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    summary = "通过" if all(step["status"] == "passed" for step in steps) else "未通过"
    return {
        "case_id": case_id,
        "summary": summary,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "steps": steps,
        "recent_trace": recent_trace[-8:],
        "recent_stderr": recent_stderr[-8:],
        "_auto_generated": True,
    }


def build_markdown(payload: dict) -> str:
    steps = payload.get("steps") or []
    trace = payload.get("recent_trace") or []
    stderr = payload.get("recent_stderr") or []
    return "\n".join(
        [
            "# Agent Runtime Happy Path Proof",
            "",
            f"- case: {payload.get('case_id', '')}",
            f"- summary: {payload.get('summary', '')}",
            f"- generated_at: {payload.get('generated_at', '')}",
            "",
            "## Steps",
            "",
            *[
                f"- {step.get('label', '')}: {step.get('status', '')}"
                + (f" · {step.get('detail')}" if step.get("detail") else "")
                for step in steps
            ],
            "",
            "## Recent Trace",
            "",
            *([f"- {json.dumps(item, ensure_ascii=False)}" for item in trace] or ["- none"]),
            "",
            "## Recent Stderr",
            "",
            *([f"- {line}" for line in stderr] or ["- none"]),
            "",
        ]
    )


def main() -> None:
    args = build_parser().parse_args()
    payload = run_gateway_happy_path(args.case_id)
    json_path, md_path = proof_paths(args.case_id)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    print(str(json_path))
    print(str(md_path))
    print(payload["summary"])


if __name__ == "__main__":
    main()
