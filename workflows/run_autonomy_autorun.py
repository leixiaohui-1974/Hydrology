#!/usr/bin/env python3
"""协智 (XieZhi) — 多智能体编排与科研

HydroMind 水智工坊 · Agent #20

自治闭环执行器：
评估 -> 执行动作 -> 再评估，直到达标或达到迭代上限。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workflows import run_workflow
from workflows._shared import WORKSPACE, run_python, write_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _to_workspace_rel(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return str(candidate.resolve().relative_to(WORKSPACE))
        except ValueError:
            return str(candidate.resolve())
    return str(candidate)


def _root_cause_hints(case_id: str) -> list[str]:
    """从关键评估工件中提取高价值根因提示。"""
    hints: list[str] = []
    strict_path = WORKSPACE / "reports" / "acceptance" / "strict_revalidation_summary.json"
    strict = _load_json(strict_path)
    control = ((strict.get("modules", {}) or {}).get("control", {}) or {})
    if control:
        pass_rate = float(control.get("pass_rate", 0.0) or 0.0)
        if pass_rate <= 0.05:
            hints.append(f"control pass_rate={pass_rate:.3f}，控制链路几乎全失败")
        failed_samples = control.get("failed_samples", []) or []
        for fs in failed_samples[:3]:
            errs = fs.get("errors", []) if isinstance(fs, dict) else []
            if errs:
                for e in errs:
                    msg = str(e).strip()
                    if msg:
                        hints.append(msg)

    rv_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "real_validation" / "real_validation_report.json"
    rv = _load_json(rv_path)
    selected = rv.get("selected_window", {}) if isinstance(rv, dict) else {}
    hours = selected.get("hours")
    if isinstance(hours, (int, float)) and float(hours) <= 1:
        hints.append("real_validation 仅选到 1 小时时窗，导致控制/调度评估不可靠")

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in actions:
        wf = str(item.get("workflow", "")).strip()
        if not wf or wf in seen:
            continue
        seen.add(wf)
        deduped.append(item)
    return deduped


def _launch_review_path(case_id: str) -> dict[str, Any]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    path_groups = {
        "strict_revalidation_summary": [WORKSPACE / "reports" / "acceptance" / "strict_revalidation_summary.json"],
        "live_dashboard": [
            contracts_dir / "E2E_LIVE_DASHBOARD.html",
            contracts_dir / "E2E_LIVE_DASHBOARD.md",
        ],
        "verification_assets": [
            contracts_dir / "outcome_coverage_report.latest.json",
            contracts_dir / "e2e_outcome_verification_report.json",
            contracts_dir / "e2e_outcome_verification_report.md",
        ],
        "release_manifest": [contracts_dir / "release_manifest.json"],
    }

    resolved: dict[str, Any] = {}
    for key, candidates in path_groups.items():
        existing = [
            str(path.relative_to(WORKSPACE))
            for path in candidates
            if path.exists()
        ]
        if not existing:
            continue
        resolved[key] = existing[0] if key in {"strict_revalidation_summary", "release_manifest"} else existing

    ordered_assets: list[str] = []
    for value in resolved.values():
        if isinstance(value, list):
            ordered_assets.extend(value)
        else:
            ordered_assets.append(value)
    if ordered_assets:
        resolved["review_sequence"] = ordered_assets
    return resolved


def _resolve_release_contract_path(case_id: str, raw_path: str | None, fallback_name: str) -> Path:
    if raw_path:
        candidate = Path(raw_path)
        return candidate if candidate.is_absolute() else (WORKSPACE / candidate)
    return WORKSPACE / "cases" / case_id / "contracts" / fallback_name


def _materialize_release_manifest(
    case_id: str,
    *,
    release_version: str | None,
    workflow_run_path: str | None,
    review_bundle_path: str | None,
    release_manifest_output: str | None,
    release_channel: str,
    release_status: str,
) -> str | None:
    release_manifest_path = _resolve_release_contract_path(case_id, release_manifest_output, "release_manifest.json")
    if release_version is None:
        return _to_workspace_rel(release_manifest_path) if release_manifest_path.exists() else None

    workflow_run = _resolve_release_contract_path(case_id, workflow_run_path, "workflow_run.json")
    review_bundle = _resolve_release_contract_path(case_id, review_bundle_path, "review_bundle.json")
    if not workflow_run.exists() or not review_bundle.exists():
        return None

    run_python(
        WORKSPACE / "Hydrology" / "workflows" / "build_release_manifest.py",
        [
            "--case-id",
            case_id,
            "--version",
            release_version,
            "--workflow-run",
            str(workflow_run),
            "--review-bundle",
            str(review_bundle),
            "--channel",
            release_channel,
            "--status",
            release_status,
            "--output",
            str(release_manifest_path),
        ],
    )
    return _to_workspace_rel(release_manifest_path) if release_manifest_path.exists() else None


def _run_assess(case_id: str, standard_config: str) -> dict[str, Any]:
    run_workflow("autonomy_assess", case_id=case_id, standard_config=standard_config)
    report_path = WORKSPACE / "cases" / case_id / "contracts" / "autonomy_assessment.latest.json"
    return _load_json(report_path)


def run_autonomy_autorun(
    case_id: str,
    standard_config: str = "Hydrology/configs/autonomy_quality_standard.yaml",
    max_rounds: int = 3,
    execution_profile: str = "default",
    stop_on_pass: bool = True,
    release_version: str | None = None,
    workflow_run_path: str | None = None,
    review_bundle_path: str | None = None,
    release_manifest_output: str | None = None,
    release_channel: str = "staging",
    release_status: str = "published",
) -> dict[str, Any]:
    """执行自治闭环，返回全过程摘要。"""
    std_path = (WORKSPACE / standard_config).resolve()
    standard = _load_yaml(std_path)
    if not standard:
        raise FileNotFoundError(f"standard config missing: {std_path}")

    fast_overrides = standard.get("fast_overrides", {}) if execution_profile == "fast_validation" else {}
    rounds: list[dict[str, Any]] = []

    prev_score: float | None = None
    stagnant_rounds = 0
    stop_reason = ""
    for round_idx in range(1, max_rounds + 1):
        assess = _run_assess(case_id, standard_config)
        judge = assess.get("judge", {})
        verdict = str(judge.get("verdict", "WARN"))
        before_score = float(judge.get("overall_score", 0.0) or 0.0)
        actions = _dedupe_actions(assess.get("recommended_actions", []))

        round_result: dict[str, Any] = {
            "round": round_idx,
            "before": {
                "verdict": verdict,
                "overall_score": before_score,
                "weak_dimensions": judge.get("weak_dimensions", []),
            },
            "actions": [],
        }

        if stop_on_pass and verdict == "PASS":
            round_result["stopped"] = "pass_reached"
            rounds.append(round_result)
            stop_reason = "pass_reached"
            break
        if not actions:
            round_result["stopped"] = "no_actions"
            rounds.append(round_result)
            stop_reason = "no_actions"
            break

        any_success = False
        for action in actions:
            wf = action["workflow"]
            kwargs: dict[str, Any] = {"case_id": case_id}
            kwargs.update(fast_overrides.get(wf, {}))
            try:
                result = run_workflow(wf, **kwargs)
                any_success = True
                round_result["actions"].append(
                    {
                        "workflow": wf,
                        "status": "passed",
                        "result_excerpt": str(result)[:300],
                    }
                )
            except Exception as exc:
                round_result["actions"].append(
                    {
                        "workflow": wf,
                        "status": "failed",
                        "error": str(exc)[:400],
                    }
                )

        assess_after = _run_assess(case_id, standard_config)
        judge_after = assess_after.get("judge", {})
        round_result["after"] = {
            "verdict": judge_after.get("verdict"),
            "overall_score": judge_after.get("overall_score"),
            "weak_dimensions": judge_after.get("weak_dimensions", []),
        }
        rounds.append(round_result)

        after_score = float(judge_after.get("overall_score", 0.0) or 0.0)
        if prev_score is not None and after_score <= prev_score + 1e-9:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        prev_score = after_score

        if stop_on_pass and judge_after.get("verdict") == "PASS":
            stop_reason = "pass_reached"
            break
        if not any_success:
            stop_reason = "all_actions_failed"
            break
        if stagnant_rounds >= 1:
            stop_reason = "no_improvement"
            break

    final_assess = _run_assess(case_id, standard_config)
    final_judge = final_assess.get("judge", {})
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "case_id": case_id,
        "standard_config": str(std_path),
        "execution_profile": execution_profile,
        "generated_at": _now_iso(),
        "rounds": rounds,
        "final": {
            "verdict": final_judge.get("verdict"),
            "overall_score": final_judge.get("overall_score"),
            "weak_dimensions": final_judge.get("weak_dimensions", []),
            "stop_reason": stop_reason or "max_rounds_reached",
            "root_cause_hints": _root_cause_hints(case_id),
        },
        "_auto_generated": True,
    }
    release_manifest_path = _materialize_release_manifest(
        case_id,
        release_version=release_version,
        workflow_run_path=workflow_run_path,
        review_bundle_path=review_bundle_path,
        release_manifest_output=release_manifest_output,
        release_channel=release_channel,
        release_status=release_status,
    )
    if release_manifest_path:
        summary["release_manifest"] = release_manifest_path
    launch_review_path = _launch_review_path(case_id)
    if launch_review_path:
        summary["launch_review_path"] = launch_review_path

    json_path = contracts_dir / "autonomy_autorun.latest.json"
    md_path = contracts_dir / "autonomy_autorun.latest.md"
    write_json(json_path, summary)

    lines = [
        f"# 自治闭环执行报告（{case_id}）",
        "",
        f"- execution_profile: {execution_profile}",
        f"- final_verdict: **{summary['final']['verdict']}**",
        f"- final_score: **{summary['final']['overall_score']}**",
        f"- rounds: {len(rounds)}",
        f"- stop_reason: {summary['final']['stop_reason']}",
        "",
        "## 轮次摘要",
        "",
        "| 轮次 | before | after | action_count |",
        "|---:|---|---|---:|",
    ]
    for r in rounds:
        lines.append(
            f"| {r['round']} | {r.get('before', {}).get('verdict')} "
            f"({r.get('before', {}).get('overall_score')}) | "
            f"{r.get('after', {}).get('verdict', '-')}"
            f" ({r.get('after', {}).get('overall_score', '-')}) | {len(r.get('actions', []))} |"
        )

    lines.extend(
        [
            "",
            "## 根因提示",
            "",
        ]
    )
    for hint in summary["final"]["root_cause_hints"]:
        lines.append(f"- {hint}")
    if not summary["final"]["root_cause_hints"]:
        lines.append("- 暂无显著根因提示")

    if launch_review_path:
        lines.extend(
            [
                "",
                "## 下游启动 / 审查路径",
                "",
            ]
        )
        strict_path = launch_review_path.get("strict_revalidation_summary")
        if strict_path:
            lines.append(f"- strict_revalidation: `{strict_path}`")
        for label, key in (
            ("live_dashboard", "live_dashboard"),
            ("verification_assets", "verification_assets"),
        ):
            items = launch_review_path.get(key, [])
            if not items:
                continue
            lines.append(f"- {label}:")
            for item in items:
                lines.append(f"  - `{item}`")
        release_manifest = launch_review_path.get("release_manifest")
        if release_manifest:
            lines.append(f"- release_manifest: `{release_manifest}`")

    lines.extend(
        [
            "",
            "## 最终薄弱项",
            "",
            "| 维度 | 当前 | 目标 | 差值 |",
            "|---|---:|---:|---:|",
        ]
    )
    for wd in summary["final"]["weak_dimensions"]:
        lines.append(
            f"| {wd['dimension']} | {wd['score']:.4f} | {wd['target']:.4f} | {wd['gap']:.4f} |"
        )
    if not summary["final"]["weak_dimensions"]:
        lines.append("| - | - | - | - |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "case_id": case_id,
        "final_verdict": summary["final"]["verdict"],
        "final_score": summary["final"]["overall_score"],
        "rounds": len(rounds),
        "json_report": str(json_path),
        "md_report": str(md_path),
        "launch_review_path": launch_review_path,
        **({"release_manifest": release_manifest_path} if release_manifest_path else {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="自治闭环自动执行")
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--standard-config",
        default="Hydrology/configs/autonomy_quality_standard.yaml",
        help="标准配置路径（相对 workspace root）",
    )
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--execution-profile", default="default", choices=["default", "fast_validation"])
    parser.add_argument("--no-stop-on-pass", action="store_true")
    parser.add_argument("--release-version", default=None, help="Optional release version to materialize release_manifest.json in the same run")
    parser.add_argument("--workflow-run-path", default=None, help="Optional workflow_run.json path for release manifest materialization")
    parser.add_argument("--review-bundle-path", default=None, help="Optional review_bundle.json path for release manifest materialization")
    parser.add_argument("--release-manifest-output", default=None, help="Optional release_manifest.json output path")
    parser.add_argument("--release-channel", default="staging", help="Release channel used when materializing release manifest")
    parser.add_argument("--release-status", default="published", help="Release status used when materializing release manifest")
    args = parser.parse_args()

    result = run_autonomy_autorun(
        case_id=args.case_id,
        standard_config=args.standard_config,
        max_rounds=args.max_rounds,
        execution_profile=args.execution_profile,
        stop_on_pass=not args.no_stop_on_pass,
        release_version=args.release_version,
        workflow_run_path=args.workflow_run_path,
        review_bundle_path=args.review_bundle_path,
        release_manifest_output=args.release_manifest_output,
        release_channel=args.release_channel,
        release_status=args.release_status,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
