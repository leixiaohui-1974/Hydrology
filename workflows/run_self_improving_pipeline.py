#!/usr/bin/env python3
"""率定 (LuDing) — 参数校准与自学习

HydroMind 水智工坊 · Agent #5

自学习自提升工作流引擎 — HydroMind Autonomous Pipeline Product。

统一编排：初始化 → 挖掘 → 建模 → 率定 → 诊断 → 提升 → 评价 → 归档。
每个阶段产出标准 JSON 合约到 cases/{case_id}/contracts/。
迭代收敛：反复运行直到全站验证期精度达标或达到最大轮次。

设计原则：
  - 零硬编码：所有参数从 YAML 加载
  - 自诊断：自动识别弱项
  - 自挖掘：自动发现更高精度数据
  - 自提升：多策略率定自动择优
  - 自报告：改进决策全程可追溯
  - 可编排：支持单阶段/批量/迭代模式

用法：
    # 全量运行单个案例
    python3 run_self_improving_pipeline.py --case-id zhongxian

    # 仅运行精度提升循环
    python3 run_self_improving_pipeline.py --case-id zhongxian --phases improve

    # 批量运行所有案例
    python3 run_self_improving_pipeline.py --batch all

    # 设置收敛目标
    python3 run_self_improving_pipeline.py --case-id zhongxian --target-nse 0.85 --max-iterations 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ── 合约读写 ──────────────────────────────────────────────────────────────

def _contracts_dir(case_id: str) -> Path:
    d = WORKSPACE / "cases" / case_id / "contracts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_contract(case_id: str, name: str, payload: Any) -> Path:
    path = _contracts_dir(case_id) / f"{name}.latest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def _read_contract(case_id: str, name: str) -> dict | None:
    path = _contracts_dir(case_id) / f"{name}.latest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _shared_hydrology_nse_stations(case_id: str) -> list[dict[str, Any]]:
    evidence = _read_contract(case_id, "hydrology_nse_evidence") or {}
    stations = evidence.get("stations") or []
    normalized: list[dict[str, Any]] = []
    for station in stations:
        validation_nse = station.get("validation_nse")
        if validation_nse is None:
            continue
        normalized.append(
            {
                "station_id": station.get("station_id"),
                "station_name": station.get("station_name") or station.get("station_id"),
                "status": "completed",
                "validation": {"nse": float(validation_nse)},
            }
        )
    return normalized


def _archive_contract(case_id: str, name: str) -> None:
    """将 latest 合约归档为带时间戳的版本。"""
    path = _contracts_dir(case_id) / f"{name}.latest.json"
    if path.exists():
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        archive = _contracts_dir(case_id) / f"{name}.{ts}.json"
        archive.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


# ── Phase: Init ───────────────────────────────────────────────────────────

def phase_init(case_id: str, cfg: dict) -> dict:
    """确保案例目录和配置存在。"""
    from workflows.run_case_init import create_case_directory
    case_dir = WORKSPACE / "cases" / case_id
    config_path = BASE_DIR / "configs" / f"{case_id}.yaml"
    if not config_path.exists():
        return {"phase": "init", "status": "error", "error": f"Config not found: {config_path.name}"}
    create_case_directory(case_id, cfg.get("display_name", case_id), cfg)
    return {"phase": "init", "status": "completed", "case_dir": str(case_dir.relative_to(WORKSPACE))}


# ── Phase: Mine ───────────────────────────────────────────────────────────

def phase_mine(case_id: str, cfg: dict) -> dict:
    """知识挖掘：坐标、参数、曲线、数据源发现。"""
    try:
        from hydro_model.knowledge_mining import run_pipeline
        from workflows._shared import resolve_config_paths
        resolved = resolve_config_paths(dict(cfg), WORKSPACE)
        result = run_pipeline(resolved)
        contract = {
            "phase": "mine",
            "status": "completed",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "stages": {k: {"count": v.get("count", 0)} for k, v in result.get("stages", {}).items()},
        }
        _write_contract(case_id, "knowledge_mining", contract)
        return contract
    except Exception as e:
        return {"phase": "mine", "status": "error", "error": str(e)}


# ── Phase: Model ──────────────────────────────────────────────────────────

def phase_model(case_id: str, cfg: dict) -> dict:
    """水文+水动力建模。"""
    import subprocess
    stages_to_run = "source_discovery,data_pack,hydrology,hydraulics_steady"
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "run_full_modeling.py"),
         "--case-id", case_id, "--stages", stages_to_run],
        capture_output=True, text=True, timeout=600,
    )
    contract = {
        "phase": "model",
        "status": "completed" if result.returncode == 0 else "error",
        "stages_run": stages_to_run,
        "returncode": result.returncode,
    }
    if result.returncode != 0:
        contract["stderr_tail"] = result.stderr[-500:] if result.stderr else ""
    _write_contract(case_id, "modeling_run", contract)
    return contract


# ── Phase: Calibrate ──────────────────────────────────────────────────────

def phase_calibrate(case_id: str, cfg: dict) -> dict:
    """逐站率定验证 → calibration_report.latest.json。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "run_calibration_report.py"),
         "--case-id", case_id],
        capture_output=True, text=True, timeout=600,
    )
    report = _read_contract(case_id, "calibration_report")
    if report:
        stations = _shared_hydrology_nse_stations(case_id) or report.get("stations", [])
        completed = [s for s in stations if s.get("status") == "completed"]
        if not stations:
            return {
                "phase": "calibrate",
                "status": "error",
                "error": "empty calibration_report",
                "returncode": result.returncode,
                "total_stations": 0,
                "completed_stations": 0,
            }

        if not completed:
            return {
                "phase": "calibrate",
                "status": "error",
                "error": "calibration_report has no completed stations",
                "returncode": result.returncode,
                "total_stations": len(stations),
                "completed_stations": 0,
            }

        val_nses = []
        for s in completed:
            v = s.get("validation", {})
            nse = v.get("nse")
            if nse is not None:
                val_nses.append(float(nse))
        if not val_nses:
            return {
                "phase": "calibrate",
                "status": "error",
                "error": "calibration_report has no validation nse",
                "returncode": result.returncode,
                "total_stations": len(stations),
                "completed_stations": len(completed),
            }
        return {
            "phase": "calibrate",
            "status": "completed",
            "total_stations": len(stations),
            "completed_stations": len(completed),
            "mean_validation_nse": sum(val_nses) / len(val_nses) if val_nses else None,
            "min_validation_nse": min(val_nses) if val_nses else None,
        }
    return {"phase": "calibrate", "status": "error", "returncode": result.returncode}


# ── Phase: Diagnose ───────────────────────────────────────────────────────

def phase_diagnose(
    case_id: str, cfg: dict, target_nse: float, config_path: str | None = None,
) -> dict:
    """诊断弱站：读取率定报告，标记 NSE < 目标的站点。"""
    from workflows._autonomy_policy import section

    report = _read_contract(case_id, "calibration_report")
    if not report:
        return {"phase": "diagnose", "status": "skipped", "reason": "no calibration report"}

    dpol = section(case_id, "diagnose", config_path)
    min_weak_audit = int(dpol.get("data_audit_min_weak_stations", 3))
    large_gap_thr = float(dpol.get("large_gap_nse_threshold", 0.15))
    stations = _shared_hydrology_nse_stations(case_id) or report.get("stations", [])

    if not stations:
        contract = {
            "phase": "diagnose",
            "status": "completed",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "target_nse": target_nse,
            "weak_stations": [],
            "strong_stations": [],
            "convergence": False,
            "reason": "empty calibration_report",
            "recommended_actions": [{
                "action": "rerun_calibration",
                "workflows": ["calibrate", "model"],
                "reason": "calibration_report_contains_no_station_results",
            }],
            "diagnose_policy_applied": {
                "data_audit_min_weak_stations": min_weak_audit,
                "large_gap_nse_threshold": large_gap_thr,
            },
        }
        _write_contract(case_id, "diagnosis", contract)
        return contract

    weak = []
    strong = []
    for s in stations:
        if s.get("status") != "completed":
            continue
        val = s.get("validation", {})
        nse = val.get("nse")
        if nse is None:
            continue
        entry = {"station_id": s["station_id"], "station_name": s["station_name"], "nse": float(nse)}
        if float(nse) < target_nse:
            weak.append(entry)
        else:
            strong.append(entry)

    if not weak and not strong:
        contract = {
            "phase": "diagnose",
            "status": "completed",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "target_nse": target_nse,
            "weak_stations": [],
            "strong_stations": [],
            "convergence": False,
            "reason": "calibration_report_missing_validation_nse",
            "recommended_actions": [{
                "action": "rerun_calibration",
                "workflows": ["calibrate", "model"],
                "reason": "calibration_report_has_no_usable_validation_metrics",
            }],
            "diagnose_policy_applied": {
                "data_audit_min_weak_stations": min_weak_audit,
                "large_gap_nse_threshold": large_gap_thr,
            },
        }
        _write_contract(case_id, "diagnosis", contract)
        return contract

    recommended_actions: list[dict[str, Any]] = []
    if weak:
        recommended_actions.append({
            "action": "run_improve",
            "workflows": ["precision_improvement", "hydraulic_precision_improvement"],
            "reason": "validation_nse_below_target",
            "target_nse": target_nse,
            "weak_count": len(weak),
        })
        if len(weak) >= min_weak_audit:
            recommended_actions.append({
                "action": "data_quality_audit",
                "workflows": ["data_audit"],
                "reason": "multiple_weak_stations_suggest_data_or_structure_review",
            })
        gap = max(target_nse - w["nse"] for w in weak)
        if gap > large_gap_thr:
            recommended_actions.append({
                "action": "dl_autolearn_or_alternate_model",
                "workflows": ["dl_autolearn", "model"],
                "reason": "large_nse_gap_may_need_ml_or_model_family_change",
                "max_gap": round(gap, 4),
            })
    else:
        recommended_actions.append({
            "action": "maintain",
            "reason": "all_reported_stations_meet_target_nse",
        })

    contract = {
        "phase": "diagnose",
        "status": "completed",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "target_nse": target_nse,
        "weak_stations": weak,
        "strong_stations": strong,
        "convergence": len(weak) == 0,
        "recommended_actions": recommended_actions,
        "diagnose_policy_applied": {
            "data_audit_min_weak_stations": min_weak_audit,
            "large_gap_nse_threshold": large_gap_thr,
        },
    }
    _write_contract(case_id, "diagnosis", contract)
    return contract


# ── Phase: Improve ────────────────────────────────────────────────────────

def phase_improve(
    case_id: str, cfg: dict, target_nse: float, max_rounds: int,
    config_path: str | None = None,
) -> dict:
    """自提升：D1 水文 + D2 水力学，多模型×多分辨率率定，择优替换。"""
    import subprocess

    from workflows._autonomy_policy import section

    results: dict[str, Any] = {"phase": "improve", "status": "completed", "dimensions": {}}

    p_pol = section(case_id, "precision_improvement", config_path)
    weak_batch = int(p_pol.get("weak_point_batch_size", 0))

    # D1: 水文精度提升
    _archive_contract(case_id, "precision_improvement")
    d1_cmd = [
        sys.executable, str(BASE_DIR / "workflows" / "run_precision_improvement.py"),
        "--case-id", case_id,
        "--threshold", str(target_nse),
        "--max-rounds", str(max_rounds),
    ]
    if config_path:
        d1_cmd.extend(["--config", config_path])
    if weak_batch > 0:
        d1_cmd.extend(["--weak-batch", str(weak_batch)])
    d1_result = subprocess.run(
        d1_cmd,
        capture_output=True, text=True, timeout=1200,
    )
    d1 = _read_contract(case_id, "precision_improvement")
    if d1:
        overall = d1.get("overall_improvement", {})
        results["dimensions"]["D1"] = {
            "status": "completed",
            "weak_count": overall.get("weak_station_count", 0),
            "improved_count": overall.get("improved_count", 0),
            "mean_nse_before": overall.get("mean_nse_before"),
            "mean_nse_after": overall.get("mean_nse_after"),
            "mean_delta": overall.get("mean_delta_nse"),
        }
    else:
        results["dimensions"]["D1"] = {"status": "error", "returncode": d1_result.returncode}

    # D2: 水力学精度提升
    _archive_contract(case_id, "hydraulic_precision_improvement")
    d2_cmd = [
        sys.executable, str(BASE_DIR / "workflows" / "run_hydraulic_precision_improvement.py"),
        "--case-id", case_id,
        "--threshold", str(target_nse),
        "--max-rounds", str(max_rounds),
    ]
    if config_path:
        d2_cmd.extend(["--config", config_path])
    d2_result = subprocess.run(
        d2_cmd,
        capture_output=True, text=True, timeout=1200,
    )
    d2 = _read_contract(case_id, "hydraulic_precision_improvement")
    if d2:
        overall = d2.get("overall_improvement", {})
        results["dimensions"]["D2"] = {
            "status": "completed",
            "weak_count": overall.get("weak_station_count", 0),
            "improved_count": overall.get("improved_count", 0),
            "mean_nse_before": overall.get("mean_nse_before"),
            "mean_nse_after": overall.get("mean_nse_after"),
            "mean_delta": overall.get("mean_delta_nse"),
        }
    else:
        results["dimensions"]["D2"] = {"status": "skipped", "note": "no D2 calibration report or error"}

    # Backward-compatible summary fields from D1
    d1_info = results["dimensions"].get("D1", {})
    results["weak_count"] = d1_info.get("weak_count", 0)
    results["improved_count"] = d1_info.get("improved_count", 0)
    results["mean_nse_before"] = d1_info.get("mean_nse_before")
    results["mean_nse_after"] = d1_info.get("mean_nse_after")
    results["mean_delta"] = d1_info.get("mean_delta")

    return results


# ── Phase: Evaluate ───────────────────────────────────────────────────────

def phase_evaluate(case_id: str, cfg: dict) -> dict:
    """综合评价：汇总所有合约，计算覆盖度和成熟度。"""
    contracts_dir = _contracts_dir(case_id)
    available = sorted(p.name for p in contracts_dir.glob("*.latest.json"))

    scores = {}
    cal = _read_contract(case_id, "calibration_report")
    if cal:
        stations = [s for s in cal.get("stations", []) if s.get("status") == "completed"]
        nses = [float(s["validation"]["nse"]) for s in stations if s.get("validation", {}).get("nse") is not None]
        scores["d1_hydro_modeling"] = {
            "mean_nse": sum(nses) / len(nses) if nses else 0,
            "min_nse": min(nses) if nses else 0,
            "station_count": len(nses),
        }

    improvement = _read_contract(case_id, "precision_improvement")
    if improvement:
        overall = improvement.get("overall_improvement", {})
        scores["self_improvement"] = {
            "rounds_run": improvement.get("max_rounds", 0),
            "improved_count": overall.get("improved_count", 0),
            "mean_delta": overall.get("mean_delta_nse"),
        }

    diagnosis = _read_contract(case_id, "diagnosis")
    convergence = False
    if diagnosis:
        convergence = diagnosis.get("convergence", False)

    expected_contracts = [
        "case_manifest",
        "calibration_report",
        "diagnosis",
        "precision_improvement",
        "data_pack",
        "delineation",
        "hydrology_sim",
        "hydraulics_steady",
        "hydraulics_unsteady",
        "autonomous_cascade_report",
        "d1d4_precision_report",
        "pipeline_report",
        "self_improving_pipeline",
    ]
    matched = [c for c in expected_contracts if any(c in a for a in available)]
    coverage = len(matched)
    coverage_pct = coverage / len(expected_contracts) * 100

    maturity_levels = {
        (0, 30): "L0_manual",
        (30, 60): "L1_assisted",
        (60, 80): "L2_partial_auto",
        (80, 95): "L3_conditional_auto",
        (95, 101): "L4_high_auto",
    }
    maturity = "unknown"
    for (lo, hi), level in maturity_levels.items():
        if lo <= coverage_pct < hi:
            maturity = level
            break

    contract = {
        "phase": "evaluate",
        "status": "completed",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "available_contracts": available,
        "coverage_pct": round(coverage_pct, 1),
        "maturity": maturity,
        "convergence": convergence,
        "dimension_scores": scores,
    }
    _write_contract(case_id, "pipeline_evaluation", contract)
    return contract


# ── 主循环：自迭代收敛 ───────────────────────────────────────────────────

ALL_PHASES = ["init", "mine", "model", "calibrate", "diagnose", "improve", "evaluate"]

PHASE_DESCRIPTIONS = {
    "init": "案例初始化（目录+配置验证）",
    "mine": "知识挖掘（坐标/参数/曲线/数据源）",
    "model": "水文水动力建模",
    "calibrate": "逐站率定验证",
    "diagnose": "弱站诊断",
    "improve": "多策略自提升",
    "evaluate": "综合评价与成熟度评估",
}


def run_pipeline(
    case_id: str,
    phases: list[str] | None = None,
    target_nse: float = 0.80,
    max_iterations: int = 3,
    max_improve_rounds: int = 3,
    config_path: str | None = None,
) -> dict:
    """运行自学习自提升管线。"""
    from workflows._autonomy_policy import argv_has, governance_source_relpath, section
    from workflows._shared import load_case_config

    pol = section(case_id, "self_improving_pipeline", config_path)
    policy_applied: dict[str, Any] = {}
    if not argv_has("--target-nse") and "target_nse" in pol:
        target_nse = float(pol["target_nse"])
        policy_applied["target_nse"] = target_nse
    if not argv_has("--max-iterations") and "max_iterations" in pol:
        max_iterations = int(pol["max_iterations"])
        policy_applied["max_iterations"] = max_iterations
    if not argv_has("--max-improve-rounds") and "max_improve_rounds" in pol:
        max_improve_rounds = int(pol["max_improve_rounds"])
        policy_applied["max_improve_rounds"] = max_improve_rounds

    cfg = load_case_config(case_id, config_path)
    active_phases = phases or ALL_PHASES
    has_improve = "improve" in active_phases

    try:
        from workflows.run_knowledge_registry import should_run, build_registry, record_run
        check = should_run(case_id, "pipeline", dimension="D1_hydrology", target_nse=target_nse)
        if not check["should_run"]:
            print(f"\n[去重保护] {check['reason']}")
            print(f"  如需强制运行，请设置更高 --target-nse 或手动清除注册表。")
            return {
                "case_id": case_id,
                "pipeline": "self_improving",
                "skipped": True,
                "reason": check["reason"],
                "existing_best": check.get("existing_best"),
            }
    except ImportError:
        pass

    report = {
        "case_id": case_id,
        "pipeline": "self_improving",
        "target_nse": target_nse,
        "max_iterations": max_iterations,
        "max_improve_rounds": max_improve_rounds,
        "started_at": datetime.utcnow().isoformat(timespec="seconds"),
        "iterations": [],
        "policy_governance": {
            "source": governance_source_relpath(),
            "policy_file": "workflow_autonomy_policy.yaml",
            "section": "self_improving_pipeline",
            "applied_from_yaml": policy_applied,
        },
    }

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"迭代 {iteration}/{max_iterations} — 案例: {case_id}")
        print(f"{'='*60}")

        iter_report = {"iteration": iteration, "phases": []}

        for phase_name in active_phases:
            desc = PHASE_DESCRIPTIONS.get(phase_name, phase_name)
            print(f"  [{phase_name}] {desc}...")

            if phase_name == "init":
                result = phase_init(case_id, cfg)
            elif phase_name == "mine":
                result = phase_mine(case_id, cfg)
            elif phase_name == "model":
                result = phase_model(case_id, cfg)
            elif phase_name == "calibrate":
                result = phase_calibrate(case_id, cfg)
            elif phase_name == "diagnose":
                result = phase_diagnose(case_id, cfg, target_nse, config_path)
            elif phase_name == "improve":
                result = phase_improve(case_id, cfg, target_nse, max_improve_rounds, config_path)
            elif phase_name == "evaluate":
                result = phase_evaluate(case_id, cfg)
            else:
                result = {"phase": phase_name, "status": "unknown_phase"}

            iter_report["phases"].append(result)
            status = result.get("status", "?")
            print(f"    → {status}")

            if status == "error":
                print(f"    错误: {result.get('error', result.get('stderr_tail', ''))[:200]}")

        convergence = False
        diag = _read_contract(case_id, "diagnosis")
        if diag and diag.get("convergence"):
            convergence = True

        iter_report["convergence"] = convergence
        report["iterations"].append(iter_report)

        if convergence:
            print(f"\n收敛！全站验证期 NSE >= {target_nse}")
            break

        if not has_improve:
            print("\n（未包含 improve 阶段，跳过后续迭代）")
            break

        if iteration < max_iterations:
            print(f"\n未收敛，弱站仍存在。准备迭代 {iteration + 1}...")

    report["converged"] = report["iterations"][-1].get("convergence", False) if report["iterations"] else False
    report["total_iterations"] = len(report["iterations"])
    report["completed_at"] = datetime.utcnow().isoformat(timespec="seconds")

    _write_contract(case_id, "self_improving_pipeline", report)
    print(f"\n管线报告: cases/{case_id}/contracts/self_improving_pipeline.latest.json")

    try:
        from workflows.run_knowledge_consolidate import consolidate
        print("\n[知识固化] 自动持久化本轮发现...")
        consolidate(
            case_id,
            config_path=config_path,
            agent="pipeline",
            summary=f"自提升管线迭代{report['total_iterations']}轮, "
                    f"{'已收敛' if report.get('converged') else '未收敛'}, "
                    f"target_nse={target_nse}",
        )
        print("  → 知识已固化到 YAML")
    except Exception as e:
        print(f"  → 知识固化失败: {e}")

    return report


def run_batch(target_nse: float, max_iterations: int, max_improve_rounds: int) -> list[dict]:
    """批量运行所有有配置的案例。"""
    configs_dir = BASE_DIR / "configs"
    results = []
    for cfg_file in sorted(configs_dir.glob("*.yaml")):
        if cfg_file.name.startswith("batch_") or cfg_file.name == "case_schema.yaml":
            continue
        case_id = cfg_file.stem
        print(f"\n{'#'*60}")
        print(f"批量: {case_id}")
        print(f"{'#'*60}")
        try:
            r = run_pipeline(
                case_id=case_id,
                target_nse=target_nse,
                max_iterations=max_iterations,
                max_improve_rounds=max_improve_rounds,
            )
            results.append({"case_id": case_id, "status": r.get("converged", False), "iterations": r.get("total_iterations", 0)})
        except Exception as e:
            results.append({"case_id": case_id, "status": "error", "error": str(e)})
    return results


def main():
    parser = argparse.ArgumentParser(
        description="HydroMind 自学习自提升工作流引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
阶段列表:
  init       案例初始化（目录+配置验证）
  mine       知识挖掘（坐标/参数/曲线/数据源）
  model      水文水动力建模
  calibrate  逐站率定验证
  diagnose   弱站诊断
  improve    多策略自提升
  evaluate   综合评价与成熟度评估

示例:
  # 全量自提升
  python3 run_self_improving_pipeline.py --case-id zhongxian --target-nse 0.85

  # 仅诊断和评价
  python3 run_self_improving_pipeline.py --case-id zhongxian --phases diagnose,evaluate

  # 批量运行所有案例
  python3 run_self_improving_pipeline.py --batch all
""",
    )
    parser.add_argument("--case-id", help="案例 ID")
    parser.add_argument("--phases", help=f"逗号分隔阶段: {','.join(ALL_PHASES)}")
    parser.add_argument("--target-nse", type=float, default=0.80, help="收敛目标 NSE（默认 0.80）")
    parser.add_argument("--max-iterations", type=int, default=3, help="最大迭代轮次（默认 3）")
    parser.add_argument("--max-improve-rounds", type=int, default=3, help="每轮率定 progressive rounds（默认 3）")
    parser.add_argument("--config", default=None, help="YAML 配置路径（可选）")
    parser.add_argument("--batch", help="'all' 批量运行所有案例")
    args = parser.parse_args()

    if args.batch:
        results = run_batch(args.target_nse, args.max_iterations, args.max_improve_rounds)
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    elif args.case_id:
        phases = args.phases.split(",") if args.phases else None
        report = run_pipeline(
            case_id=args.case_id,
            phases=phases,
            target_nse=args.target_nse,
            max_iterations=args.max_iterations,
            max_improve_rounds=args.max_improve_rounds,
            config_path=args.config,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        parser.error("需要 --case-id 或 --batch all")


if __name__ == "__main__":
    main()
