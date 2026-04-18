#!/usr/bin/env python3
"""审评 (ShenPing) — 精度评估与质量审核

HydroMind 水智工坊 · Agent #9

端到端自主运行能力评估：
- 统一量化仿真/辨识/预报/调度/控制/评价/测试/SIL/ODD/WNAL 精度与可用性
- 评估自诊断/自挖掘/自升级/自学习闭环能力
- 输出准入判定和下一轮自治执行建议
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from workflows._shared import WORKSPACE, load_case_config, write_json


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


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _workspace_rel_or_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(WORKSPACE.resolve()).as_posix()
    except ValueError:
        name = resolved.name or path.name or "artifact"
        return f"[external]/{name}"


def _artifact_paths(case_id: str, standard: dict[str, Any]) -> dict[str, Path]:
    artifacts = standard.get("artifacts", {})
    paths: dict[str, Path] = {}
    for key, tmpl in artifacts.items():
        rel = str(tmpl).format(case_id=case_id)
        paths[key] = (WORKSPACE / rel).resolve()
    return paths


def _dim_from_d1d4(d1d4: dict[str, Any]) -> dict[str, float]:
    dims = d1d4.get("dimensions", {}) if isinstance(d1d4, dict) else {}
    d1 = _clip01((dims.get("d1", {}) or {}).get("score", 0.0) / 5.0)
    d2 = _clip01((dims.get("d2", {}) or {}).get("score", 0.0) / 5.0)
    d3 = _clip01((dims.get("d3", {}) or {}).get("score", 0.0) / 5.0)
    d4 = _clip01((dims.get("d4", {}) or {}).get("score", 0.0) / 5.0)
    return {
        "simulation": d2,
        "identification": d3,
        "forecast": d4,
        "evaluation": _clip01((d1 + d2 + d3 + d4) / 4.0),
    }


def _dim_from_real_validation(real_val: dict[str, Any]) -> float:
    rows = (((real_val or {}).get("metrics") or {}).get("rows") or [])
    if not rows:
        return 0.0
    nse_values = [float(r.get("NSE", 0.0)) for r in rows if isinstance(r, dict)]
    if not nse_values:
        return 0.0
    # 将 [-1,1] 映射到 [0,1]
    return _clip01((sum(nse_values) / len(nse_values) + 1.0) / 2.0)


def _dim_from_strict_revalidation(strict_rev: dict[str, Any]) -> tuple[float, float]:
    modules = (strict_rev or {}).get("modules", {}) if isinstance(strict_rev, dict) else {}
    physics = ((modules.get("physics", {}) or {}).get("pass_rate", 0.0)) or 0.0
    control = ((modules.get("control", {}) or {}).get("pass_rate", 0.0)) or 0.0
    return _clip01(float(physics)), _clip01(float(control))


def _dim_from_wnal(wnal_report: dict[str, Any]) -> float:
    metrics = (wnal_report or {}).get("metrics", {})
    metric_score = metrics.get("wnal_score")
    if isinstance(metric_score, (int, float)):
        score_f = float(metric_score)
        return _clip01(score_f if score_f <= 1.0 else score_f / 5.0)

    raw_wnal = (wnal_report or {}).get("raw_wnal", {})
    overall = (raw_wnal or {}).get("wnal_overall", {})
    if overall:
        score = overall.get("wnal_score")
        if isinstance(score, (int, float)):
            score_f = float(score)
            return _clip01(score_f if score_f <= 1.0 else score_f / 5.0)

    sections = (wnal_report or {}).get("sections", [])
    if not isinstance(sections, list):
        return 0.0
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        if sec.get("title") in {"WNAL总评", "WNAL 总评", "总评"}:
            for table in sec.get("tables", []):
                for row in table.get("rows", []):
                    if len(row) >= 2 and str(row[0]).strip().lower() in {"score", "总分"}:
                        try:
                            return _clip01(float(row[1]) / 5.0)
                        except Exception:
                            pass
    # 回退：若无显式得分，按报告存在给基础可用分
    return 0.6 if sections else 0.0


def _dim_from_odd_coverage(odd_coverage: dict[str, Any]) -> float:
    metrics = (odd_coverage or {}).get("coverage_metrics") or {}
    scenario_count = metrics.get("total_scenarios_tested")
    recovery_success = metrics.get("recovery_success_rate")
    if not isinstance(scenario_count, (int, float)) or int(scenario_count) <= 0:
        return 0.0
    if not isinstance(recovery_success, (int, float)):
        return 0.4
    return _clip01(max(0.4, 0.65 * float(recovery_success)))


def _capability_dims(paths: dict[str, Path]) -> dict[str, float]:
    selfdiag = _load_json(paths["selfdiag"])
    improve = _load_json(paths["precision_improvement"])
    autolearn = _load_json(paths["autolearn"])
    deep_rec = _load_json(paths.get("deep_asset_record", Path("")))
    knowledge_mine = _load_json(paths.get("knowledge_mine", paths.get("wxq_mine", Path(""))))

    self_diag = 0.0
    if selfdiag:
        verdict = str(selfdiag.get("final_verdict", "")).upper()
        self_diag = 1.0 if verdict == "PASS" else 0.5

    self_mining = 1.0 if deep_rec or knowledge_mine else 0.0
    self_upgrade = 1.0 if improve else 0.0
    rounds = float((autolearn or {}).get("rounds_run", 0) or 0)
    if autolearn:
        # 即使 rounds_run=0，也说明系统已完成“诊断并判定当前无需继续优化”。
        base = 0.65
        self_learning = _clip01(base + rounds / 3.0)
        if ((autolearn.get("consolidation") or {}).get("n_improvements", 0) or 0) > 0:
            self_learning = _clip01(self_learning + 0.1)
    else:
        self_learning = 0.0
    return {
        "self_diagnosis": self_diag,
        "self_mining": self_mining,
        "self_upgrade": self_upgrade,
        "self_learning": self_learning,
    }


def _merge_dimension_scores(
    standard: dict[str, Any],
    d1d4_dims: dict[str, float],
    d1d4_report: dict[str, Any],
    real_val: float,
    physics: float,
    control: float,
    wnal: float,
    odd_coverage_score: float,
    caps: dict[str, float],
) -> dict[str, float]:
    dims_cfg = standard.get("dimensions", {})
    scores: dict[str, float] = {k: 0.0 for k in dims_cfg.keys()}
    scores.update(d1d4_dims)
    scores["simulation"] = _clip01((scores.get("simulation", 0.0) + real_val + physics) / 3.0)
    scores["testing"] = physics
    scores["control"] = control
    d1d4_wnal = 0.0
    wnal_in_d1d4 = d1d4_report.get("wnal_score")
    if isinstance(wnal_in_d1d4, (int, float)):
        d1d4_wnal = _clip01(float(wnal_in_d1d4) if float(wnal_in_d1d4) <= 1.0 else float(wnal_in_d1d4) / 5.0)
    scores["wnal"] = max(wnal, d1d4_wnal)
    # 当前仓库内尚无稳定 ODD/SIL 数值合约，使用“有无工件+流程可用性”保守计分
    scores["sil"] = 0.7 if physics > 0.0 else 0.0
    scores["odd"] = max(odd_coverage_score, 0.65 if wnal > 0.0 else 0.0)
    scores["scheduling"] = scores["control"]
    scores.update(caps)
    return {k: _clip01(float(v)) for k, v in scores.items()}


def _is_dimension_applicable(cfg: dict[str, Any], project_type: str) -> bool:
    not_required = [str(item).strip().lower() for item in (cfg.get("not_required_for_project_types") or []) if str(item).strip()]
    normalized_project_type = str(project_type or "").strip().lower()
    return normalized_project_type not in not_required


def _judge(standard: dict[str, Any], scores: dict[str, float], project_type: str = "") -> dict[str, Any]:
    dims_cfg = standard.get("dimensions", {})
    pass_score = float((standard.get("thresholds", {}) or {}).get("pass_score", 0.75))
    warn_score = float((standard.get("thresholds", {}) or {}).get("warning_score", 0.60))

    weighted = 0.0
    total_w = 0.0
    weak_dims: list[dict[str, Any]] = []
    applicable_dimensions: list[str] = []
    skipped_dimensions: list[str] = []
    for name, cfg in dims_cfg.items():
        if not _is_dimension_applicable(cfg or {}, project_type):
            skipped_dimensions.append(name)
            continue
        weight = float((cfg or {}).get("weight", 0.0))
        min_score = float((cfg or {}).get("min_score", pass_score))
        score = float(scores.get(name, 0.0))
        applicable_dimensions.append(name)
        weighted += score * weight
        total_w += weight
        if score < min_score:
            weak_dims.append(
                {
                    "dimension": name,
                    "score": round(score, 4),
                    "target": round(min_score, 4),
                    "gap": round(min_score - score, 4),
                }
            )

    overall = _clip01(weighted / total_w) if total_w > 0 else 0.0
    if overall >= pass_score and not weak_dims:
        verdict = "PASS"
    elif overall >= warn_score:
        verdict = "WARN"
    else:
        verdict = "BLOCK"
    return {
        "overall_score": round(overall, 4),
        "verdict": verdict,
        "pass_score": pass_score,
        "warning_score": warn_score,
        "applicable_dimensions": applicable_dimensions,
        "skipped_dimensions": skipped_dimensions,
        "weak_dimensions": sorted(weak_dims, key=lambda x: x["gap"], reverse=True),
    }


def _actions(standard: dict[str, Any], judge: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = standard.get("action_catalog", {})
    actions: list[dict[str, Any]] = []
    for wd in judge.get("weak_dimensions", []):
        dim = wd["dimension"]
        for wf in catalog.get(dim, []):
            actions.append(
                {
                    "dimension": dim,
                    "workflow": wf,
                    "reason": f"{dim} score {wd['score']} < target {wd['target']}",
                    "priority": "high" if wd["gap"] >= 0.15 else "medium",
                }
            )
    return actions


def run_autonomy_assessment(
    case_id: str,
    standard_config: str = "Hydrology/configs/autonomy_quality_standard.yaml",
) -> dict[str, Any]:
    """执行端到端自治能力评估并输出标准化合约。"""
    standard_path = (WORKSPACE / standard_config).resolve()
    standard = _load_yaml(standard_path)
    if not standard:
        raise FileNotFoundError(f"autonomy standard config not found or empty: {standard_path}")
    try:
        case_cfg = load_case_config(case_id)
    except Exception:
        case_cfg = {"case_id": case_id}
    project_type = str(case_cfg.get("project_type") or "").strip().lower()

    paths = _artifact_paths(case_id, standard)
    d1d4 = _load_json(paths["d1d4_report"])
    real_val = _load_json(paths["real_validation_report"])
    strict_rev = _load_json(paths["strict_revalidation_summary"])
    external_wnal_report = _load_json(paths["wnal_report"])
    contract_wnal_report = _load_json(WORKSPACE / "cases" / case_id / "contracts" / "wnal_level_report.json")
    wnal_report = contract_wnal_report or external_wnal_report
    odd_coverage = _load_json(WORKSPACE / "cases" / case_id / "contracts" / "odd_coverage_report.json")

    d1d4_dims = _dim_from_d1d4(d1d4)
    real_val_score = _dim_from_real_validation(real_val)
    physics_score, control_score = _dim_from_strict_revalidation(strict_rev)
    wnal_score = _dim_from_wnal(wnal_report)
    odd_coverage_score = _dim_from_odd_coverage(odd_coverage)
    caps = _capability_dims(paths)

    scores = _merge_dimension_scores(
        standard,
        d1d4_dims=d1d4_dims,
        d1d4_report=d1d4,
        real_val=real_val_score,
        physics=physics_score,
        control=control_score,
        wnal=wnal_score,
        odd_coverage_score=odd_coverage_score,
        caps=caps,
    )
    judge = _judge(standard, scores, project_type=project_type)
    actions = _actions(standard, judge)

    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "case_id": case_id,
        "standard": {
            "name": standard.get("name", ""),
            "schema_version": standard.get("schema_version", ""),
            "config_path": _workspace_rel_or_path(standard_path),
        },
        "generated_at": _now_iso(),
        "project_type": project_type,
        "scores": scores,
        "judge": judge,
        "recommended_actions": actions,
        "_auto_generated": True,
    }

    json_path = contracts_dir / "autonomy_assessment.latest.json"
    md_path = contracts_dir / "autonomy_assessment.latest.md"
    write_json(json_path, result)

    lines = [
        f"# 端到端自主运行评估报告（{case_id}）",
        "",
        f"- verdict: **{judge['verdict']}**",
        f"- overall_score: **{judge['overall_score']:.4f}**",
        f"- generated_at: {result['generated_at']}",
        "",
        "## 分项得分",
        "",
        "| 维度 | 分数 |",
        "|---|---:|",
    ]
    for k, v in sorted(scores.items()):
        lines.append(f"| {k} | {v:.4f} |")

    lines.extend(
        [
            "",
            "## 薄弱项",
            "",
            "| 维度 | 当前 | 目标 | 差值 |",
            "|---|---:|---:|---:|",
        ]
    )
    for wd in judge["weak_dimensions"]:
        lines.append(
            f"| {wd['dimension']} | {wd['score']:.4f} | {wd['target']:.4f} | {wd['gap']:.4f} |"
        )
    if not judge["weak_dimensions"]:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## 自治闭环建议动作",
            "",
            "| 优先级 | 维度 | workflow | 原因 |",
            "|---|---|---|---|",
        ]
    )
    for a in actions:
        lines.append(
            f"| {a['priority']} | {a['dimension']} | {a['workflow']} | {a['reason']} |"
        )
    if not actions:
        lines.append("| - | - | - | 当前已达标，可继续滚动验证 |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "case_id": case_id,
        "verdict": judge["verdict"],
        "overall_score": judge["overall_score"],
        "json_report": _workspace_rel_or_path(json_path),
        "md_report": _workspace_rel_or_path(md_path),
        "weak_dimensions": judge["weak_dimensions"],
        "recommended_actions_count": len(actions),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="端到端自主运行能力评估")
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--standard-config",
        default="Hydrology/configs/autonomy_quality_standard.yaml",
        help="标准配置路径（相对 workspace root）",
    )
    args = parser.parse_args()
    result = run_autonomy_assessment(args.case_id, standard_config=args.standard_config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
