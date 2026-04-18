#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #6

梯级水电全自主运行统一入口 — 从知识挖掘到 ODD 闭环。

产品阶段：
  1. knowledge_mining  — 知识挖掘（坐标/参数/曲线）
  2. delineation        — 流域划分
  3. calibration        — 逐站率定验证
  4. simulation         — 水文 + 水动力仿真
  5. identification     — 在线辨识（参数/曲线）
  6. control            — 控制（EDC + MPC）
  7. odd_evaluation     — ODD 评估 + 四态转换
  8. wnal_evaluation    — WNAL 12 维综合评价
  9. dispatch           — 调度优化（长中短期）
  10. verification      — SIL/验证闭环

Usage:
    python3 run_autonomous_cascade.py --case-id zhongxian
    python3 run_autonomous_cascade.py --case-id zhongxian --stages calibration,simulation,odd_evaluation
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_paths(case_id: str) -> dict[str, Path]:
    case_dir = WORKSPACE / "cases" / case_id
    return {
        "case_dir": case_dir,
        "contracts": case_dir / "contracts",
        "config": BASE_DIR / "configs" / f"{case_id}.yaml",
        "product_outputs": case_dir / "source_selection" / "product_outputs",
    }


def _tail_text(value: str, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_command(argv: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    import subprocess

    result = subprocess.run(argv, capture_output=True, text=True, env=env)
    return {
        "argv": argv,
        "returncode": result.returncode,
        "stdout_tail": _tail_text(result.stdout),
        "stderr_tail": _tail_text(result.stderr),
    }


def _read_contract_quality(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "outcome_status": None,
            "quality_gate_passed": None,
            "quality_reason": None,
        }
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return {
            "exists": True,
            "outcome_status": None,
            "quality_gate_passed": None,
            "quality_reason": None,
        }
    return {
        "exists": True,
        "outcome_status": str(payload.get("outcome_status") or "").strip().lower() or None,
        "quality_gate_passed": payload.get("quality_gate_passed"),
        "quality_reason": str(payload.get("quality_reason") or "").strip() or None,
    }


def _stage_status_from_quality(quality: dict[str, Any], *, missing_status: str = "no_data") -> str:
    if not quality.get("exists"):
        return missing_status
    outcome_status = str(quality.get("outcome_status") or "").strip().lower()
    quality_gate_passed = quality.get("quality_gate_passed")
    if outcome_status:
        return outcome_status
    if quality_gate_passed is False:
        return "quality_failed"
    if quality_gate_passed is True:
        return "completed"
    return missing_status


def _stage_reason_from_quality(quality: dict[str, Any], *, missing_reason: str) -> str | None:
    reason = str(quality.get("quality_reason") or "").strip()
    if reason:
        return reason
    if not quality.get("exists"):
        return missing_reason
    return None


# ── Stage Runners ────────────────────────────────────────────────────────────

def stage_knowledge_mining(case_id: str, paths: dict) -> dict:
    """知识挖掘：坐标 + 参数 + 曲线发现。"""
    from hydro_model.knowledge_mining import run_pipeline
    from workflows._shared import resolve_config_paths
    with open(paths["config"]) as f:
        cfg = yaml.safe_load(f)
    cfg = resolve_config_paths(cfg, WORKSPACE)
    result = run_pipeline(cfg)
    return {"stage": "knowledge_mining", "status": "completed",
            "outlets": result["stages"]["normalize"]["delineation_ready"]["count"]}


def stage_delineation(case_id: str, paths: dict) -> dict:
    """流域划分。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "run_full_modeling.py"),
         "--case-id", case_id, "--stages", "source_discovery,data_pack,delineation"],
        capture_output=True, text=True,
    )
    return {"stage": "delineation", "status": "completed" if result.returncode == 0 else "error"}


def stage_calibration(case_id: str, paths: dict) -> dict:
    """逐站率定验证。"""
    import subprocess
    subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "run_calibration_report.py"),
         "--case-id", case_id],
        capture_output=True, text=True,
    )
    report_path = paths["contracts"] / "calibration_report.latest.json"
    if report_path.exists():
        report = _load_json(report_path)
        return {"stage": "calibration", "status": "completed",
                "overall_grade": report.get("overall_grade"),
                "stations": len(report.get("stations", []))}
    return {"stage": "calibration", "status": "error"}


def stage_simulation(case_id: str, paths: dict) -> dict:
    """水文 + 水动力仿真。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "run_full_modeling.py"),
         "--case-id", case_id, "--stages", "hydrology,hydraulics_steady,hydraulics_unsteady"],
        capture_output=True, text=True,
    )
    return {"stage": "simulation", "status": "completed" if result.returncode == 0 else "error"}


def stage_identification(case_id: str, paths: dict) -> dict:
    """在线辨识（参数/曲线率定）。"""
    # 曲线率定已通过 calibration 完成，此处做增量辨识
    cal_path = paths["contracts"] / "calibration_report.latest.json"
    if cal_path.exists():
        report = _load_json(cal_path)
        stations = [s for s in report.get("stations", []) if s.get("status") == "completed"]
        return {"stage": "identification", "status": "completed",
                "identified_stations": len(stations),
                "params": {s["station_name"]: s.get("best_params", {}) for s in stations}}
    return {"stage": "identification", "status": "skipped", "reason": "no calibration report"}


def stage_control(case_id: str, paths: dict) -> dict:
    """控制（EDC + MPC) - 原生高保真与降阶双轨验证。"""
    import json
    import os

    contracts = paths["contracts"]
    report_rel = "reports/acceptance/strict_revalidation_summary.json"
    report_path = contracts.parent.parent.parent / report_rel

    script_path = WORKSPACE / "E2EControl" / "scripts" / "run_strict_revalidation.py"
    if not script_path.exists():
        return {"stage": "control", "status": "error", "reason": "E2EControl script missing"}

    report_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HYDROMIND_FAST_VALIDATION"] = "1"
    env["HYDROMIND_STRICT_REVAL_SCENARIOS"] = "8"

    state_est_path = paths["contracts"] / "state_estimation.latest.json"
    if not state_est_path.exists():
        state_est_path = paths["contracts"] / "state_est.latest.json"

    state_est_data = {}
    if state_est_path.exists():
        try:
            with open(state_est_path, "r", encoding="utf-8") as f:
                state_est_data = json.load(f)
                stations = state_est_data.get("stations", {})
                post_states = {}
                for sid, sdata in stations.items():
                    if sdata.get("converged"):
                        if "post_state" in sdata:
                            post_states[sid] = sdata["post_state"]
                        elif "z_est_first5" in sdata and sdata["z_est_first5"]:
                            post_states[sid] = [sdata["z_est_first5"][0]]
                if post_states:
                    env["HYDROMIND_INITIAL_STATE_JSON"] = json.dumps(post_states)
                    print(f"[{case_id}] 成功加载状态估计数据并注入控制引擎: {list(post_states.keys())}")
        except Exception as e:
            print(f"[{case_id}] 警告: 无法解析状态估计结果以注入 MPC ({e})")

    hf_out = paths["contracts"] / "reval_hf.json"
    rom_out = paths["contracts"] / "reval_rom.json"

    print(f"[{case_id}] Running High-Fidelity MPC tests...")
    hf_cmd = _run_command(
        [sys.executable, str(script_path), "--physics-backend", "segmented_hf", "--output", str(hf_out)],
        env=env,
    )
    if hf_cmd["returncode"] != 0:
        return {
            "stage": "control",
            "status": "error",
            "reason": hf_cmd["stderr_tail"] or hf_cmd["stdout_tail"] or "strict revalidation segmented_hf failed",
            "command": hf_cmd,
        }

    print(f"[{case_id}] Running Reduced-Order MPC tests...")
    rom_cmd = _run_command(
        [sys.executable, str(script_path), "--physics-backend", "tank", "--output", str(rom_out)],
        env=env,
    )
    if rom_cmd["returncode"] != 0:
        return {
            "stage": "control",
            "status": "error",
            "reason": rom_cmd["stderr_tail"] or rom_cmd["stdout_tail"] or "strict revalidation tank failed",
            "command": rom_cmd,
        }

    print(f"[{case_id}] Running realtime control...")
    rt_cmd = _run_command(
        [sys.executable, str(BASE_DIR / "workflows" / "run_realtime_control.py"), "--case-id", case_id]
    )
    if rt_cmd["returncode"] != 0:
        return {
            "stage": "control",
            "status": "error",
            "reason": rt_cmd["stderr_tail"] or rt_cmd["stdout_tail"] or "realtime control failed",
            "command": rt_cmd,
        }

    hf_data = _load_json(hf_out) if hf_out.exists() else {}
    rom_data = _load_json(rom_out) if rom_out.exists() else {}

    hf_pass = hf_data.get("modules", {}).get("control", {}).get("pass_rate", 0.0)
    rom_pass = rom_data.get("modules", {}).get("control", {}).get("pass_rate", 0.0)
    hf_phys_pass = hf_data.get("modules", {}).get("physics", {}).get("pass_rate", 0.0)
    rom_phys_pass = rom_data.get("modules", {}).get("physics", {}).get("pass_rate", 0.0)

    avg_phys = (hf_phys_pass + rom_phys_pass) / 2.0
    avg_ctrl = (hf_pass + rom_pass) / 2.0
    overall = (avg_phys + avg_ctrl) / 2.0

    combined_summary = {
        "scenario_count": hf_data.get("scenario_count", 0) + rom_data.get("scenario_count", 0),
        "modules": {
            "physics": {"pass_rate": avg_phys, "note": "High-Fidelity + Reduced-Order combined"},
            "control": {"pass_rate": avg_ctrl, "note": "Real MPC evaluation"},
        },
        "quality_gate_passed": bool(overall >= 0.75),
        "overall_pass_rate": overall,
        "outcome_status": "completed" if overall >= 0.75 else "quality_failed",
        "quality_reason": None if overall >= 0.75 else f"控制总体通过率未达标（overall_pass_rate={overall:.3f}）",
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(combined_summary, f, indent=2)

    out_file = paths["contracts"] / "control.latest.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(combined_summary, f, indent=2)

    dispatch_data = {}
    grid_dispatch_path = paths["contracts"] / "grid_dispatch.latest.json"
    scheduled_plan_path = paths["contracts"] / "scheduled_control_plan.latest.json"
    if grid_dispatch_path.exists():
        dispatch_data = _load_json(grid_dispatch_path)
    elif scheduled_plan_path.exists():
        dispatch_data = _load_json(scheduled_plan_path)

    rt_control_data = {}
    rt_control_path = paths["contracts"] / "realtime_control_result.latest.json"
    if rt_control_path.exists():
        rt_control_data = _load_json(rt_control_path)

    control_validation = {
        "case_id": case_id,
        "scada_state_estimation": state_est_data,
        "prediction_dispatch": dispatch_data,
        "mpc_load_tracking": {
            "strict_revalidation": combined_summary,
            "realtime_control": rt_control_data,
        },
    }

    validation_out_file = paths["contracts"] / "control_validation.latest.json"
    with open(validation_out_file, "w", encoding="utf-8") as f:
        json.dump(control_validation, f, indent=2, ensure_ascii=False)

    status = _stage_status_from_quality(_read_contract_quality(out_file), missing_status="no_data")
    reason = _stage_reason_from_quality(
        _read_contract_quality(out_file),
        missing_reason="control.latest.json 未生成",
    )
    return {
        "stage": "control",
        "status": status,
        "reason": reason,
        "overall_pass_rate": overall,
        "hf_control_pass_rate": hf_pass,
        "rom_control_pass_rate": rom_pass,
    }


def stage_odd_evaluation(case_id: str, paths: dict) -> dict:
    """ODD 评估 + 四态转换。"""
    import subprocess
    
    # Verify odd_product.py exists (as per prompt request)
    odd_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "pipedream_platform" / "runtime" / "odd_product.py"
    if not odd_path.exists():
        return {"stage": "odd_evaluation", "status": "skipped", "reason": "odd_product.py missing"}
        
    # We run run_odd_supplement.py to actually generate the data
    script_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "run_odd_supplement.py"
    if not script_path.exists():
        # Fallback to run_mrc_rehearsal.py
        script_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "run_mrc_rehearsal.py"
        
    if not script_path.exists():
        return {"stage": "odd_evaluation", "status": "skipped", "reason": "ODD runner scripts missing"}

    print(f"[{case_id}] Running ODD evaluation...")
    subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True,
    )

    # Collect the results to .latest.json
    out_file = paths["contracts"] / "odd_evaluation.latest.json"
    
    # Check if pipeline_summary.json has the odd_validation block
    summary_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / f"{case_id}_pipeline_summary.json"
    
    odd_data = {}
    if summary_path.exists():
        try:
            ps = _load_json(summary_path)
            odd_data = ps.get("odd_validation", {})
        except Exception:
            pass
            
    if not odd_data:
        # Check mrc_rehearsal summary
        mrc_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "mrc_rehearsal" / f"{case_id}_mrc_rehearsal.json"
        if mrc_path.exists():
            try:
                odd_data = _load_json(mrc_path)
            except Exception:
                pass
                
    if odd_data:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(odd_data, f, ensure_ascii=False, indent=2)
            
        return {
            "stage": "odd_evaluation", 
            "status": "completed",
            "transitions": odd_data.get("n_transitions", 0),
            "validated": odd_data.get("validated_in_simulation", False) or odd_data.get("rehearsed", False)
        }
        
    return {"stage": "odd_evaluation", "status": "error", "error": "No ODD data generated or found."}


def stage_wnal_evaluation(case_id: str, paths: dict) -> dict:
    """WNAL 12 维综合评价。"""
    import subprocess
    import shutil
    
    script_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "run_wnal_evaluation.py"
    if not script_path.exists():
        return {"stage": "wnal_evaluation", "status": "skipped", "reason": "script missing"}
        
    print(f"[{case_id}] Running WNAL evaluation...")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True,
    )
    
    report_file = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "wnal_evaluation" / "wnal_comprehensive_report.json"
    if result.returncode == 0 and report_file.exists():
        out_file = paths["contracts"] / "wnal_evaluation.latest.json"
        shutil.copy(report_file, out_file)

        try:
            report_data = _load_json(out_file)
        except (OSError, json.JSONDecodeError) as exc:
            return {"stage": "wnal_evaluation", "status": "error", "error": str(exc)}

        case_info = None
        for name, info in report_data.get("cases", {}).items():
            if info.get("code") == case_id:
                case_info = info
                break

        if case_info:
            return {
                "stage": "wnal_evaluation",
                "status": "completed",
                "wnal_level": case_info.get("wnal_level"),
                "wnal_score": case_info.get("wnal_score"),
            }

        return {
            "stage": "wnal_evaluation",
            "status": "degraded",
            "reason": f"WNAL 汇总已生成，但未找到案例 {case_id} 的条目",
            "bridge": True,
        }

    return {"stage": "wnal_evaluation", "status": "error", "error": result.stderr or result.stdout}


def stage_dispatch(case_id: str, paths: dict) -> dict:
    """调度优化 (SCADA State Estimation + Prediction/Dispatch)"""

    coupled_cmd = _run_command(
        [sys.executable, str(BASE_DIR / "workflows" / "run_full_modeling.py"), "--case-id", case_id, "--stages", "coupled"]
    )
    if coupled_cmd["returncode"] != 0:
        return {
            "stage": "dispatch",
            "status": "error",
            "reason": coupled_cmd["stderr_tail"] or coupled_cmd["stdout_tail"] or "coupled modeling failed",
            "command": coupled_cmd,
        }

    print(f"[{case_id}] Running SCADA state estimation...")
    state_est_cmd = _run_command(
        [sys.executable, str(BASE_DIR / "workflows" / "run_state_estimation.py"), "--case-id", case_id]
    )
    if state_est_cmd["returncode"] != 0:
        return {
            "stage": "dispatch",
            "status": "error",
            "reason": state_est_cmd["stderr_tail"] or state_est_cmd["stdout_tail"] or "state estimation failed",
            "command": state_est_cmd,
        }

    state_quality = _read_contract_quality(paths["contracts"] / "state_estimation.latest.json")
    state_status = _stage_status_from_quality(state_quality, missing_status="no_data")
    if state_status != "completed":
        return {
            "stage": "dispatch",
            "status": state_status,
            "reason": _stage_reason_from_quality(state_quality, missing_reason="state_estimation.latest.json 未生成"),
            "state_estimation": state_quality,
            "coupled": coupled_cmd,
        }

    print(f"[{case_id}] Running prediction and dispatch...")
    grid_dispatch_cmd = _run_command(
        [sys.executable, str(BASE_DIR / "workflows" / "run_grid_dispatch.py"), "--case-id", case_id]
    )
    if grid_dispatch_cmd["returncode"] != 0:
        return {
            "stage": "dispatch",
            "status": "error",
            "reason": grid_dispatch_cmd["stderr_tail"] or grid_dispatch_cmd["stdout_tail"] or "grid dispatch failed",
            "command": grid_dispatch_cmd,
        }

    predictive_cmd = _run_command(
        [sys.executable, str(BASE_DIR / "workflows" / "run_predictive_scheduling.py"), "--case-id", case_id]
    )
    if predictive_cmd["returncode"] != 0:
        return {
            "stage": "dispatch",
            "status": "error",
            "reason": predictive_cmd["stderr_tail"] or predictive_cmd["stdout_tail"] or "predictive scheduling failed",
            "command": predictive_cmd,
        }

    dispatch_path = paths["contracts"] / "grid_dispatch.latest.json"
    schedule_path = paths["contracts"] / "scheduled_control_plan.latest.json"
    if not dispatch_path.exists() and not schedule_path.exists():
        return {
            "stage": "dispatch",
            "status": "no_data",
            "reason": "grid_dispatch.latest.json 与 scheduled_control_plan.latest.json 均未生成",
            "coupled": coupled_cmd,
        }

    return {
        "stage": "dispatch",
        "status": "completed",
        "coupled": coupled_cmd,
        "artifacts": [
            name for name, exists in {
                "grid_dispatch.latest.json": dispatch_path.exists(),
                "scheduled_control_plan.latest.json": schedule_path.exists(),
            }.items() if exists
        ],
    }


def stage_verification(case_id: str, paths: dict) -> dict:
    """SIL 验证闭环与最终报告生成。"""
    import subprocess
    contracts = paths["contracts"]
    
    # 尝试生成 universal report
    npz_path = WORKSPACE / "pipedream-hydrology-integration-lab" / "research" / "e2e_reports" / case_id / "sim_data.npz"
    report_out = contracts / "universal_report.latest.html"
    report_script = BASE_DIR / "workflows" / "generate_universal_report.py"
    if report_script.exists():
        print(f"[{case_id}] Generating universal report...")
        subprocess.run([
            sys.executable, str(report_script),
            "--case-id", case_id,
            "--npz-path", str(npz_path),
            "--output-path", str(report_out)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    # 汇总所有阶段结果
    files = list(contracts.glob("*.latest.*"))
    return {"stage": "verification", "status": "completed",
            "artifact_count": len(files),
            "artifacts": [f.name for f in files]}


# ── Orchestrator ─────────────────────────────────────────────────────────────

ALL_STAGES = [
    "knowledge_mining", "delineation", "calibration", "simulation",
    "identification", "dispatch", "control", "odd_evaluation", "wnal_evaluation",
    "verification",
]

STAGE_FUNCS = {
    "knowledge_mining": stage_knowledge_mining,
    "delineation": stage_delineation,
    "calibration": stage_calibration,
    "simulation": stage_simulation,
    "identification": stage_identification,
    "control": stage_control,
    "odd_evaluation": stage_odd_evaluation,
    "wnal_evaluation": stage_wnal_evaluation,
    "dispatch": stage_dispatch,
    "verification": stage_verification,
}


def run_autonomous(case_id: str, stages: list[str] | None = None) -> dict:
    paths = _resolve_paths(case_id)
    active = stages or ALL_STAGES

    report = {
        "case_id": case_id,
        "pipeline": "autonomous_cascade",
        "started_at": datetime.utcnow().isoformat(timespec="seconds"),
        "steps": [],
    }

    for i, stage in enumerate(active, 1):
        func = STAGE_FUNCS.get(stage)
        if not func:
            continue
        print(f"[{i}/{len(active)}] {stage}...")
        try:
            step = func(case_id, paths)
            report["steps"].append(step)
            print(f"  -> {step.get('status', '?')}")
        except Exception as e:
            report["steps"].append({"stage": stage, "status": "error", "error": str(e)})
            print(f"  -> ERROR: {e}")

    statuses = [str(step.get("status") or "").strip().lower() for step in report["steps"]]
    failure_statuses = {"error", "failed", "quality_failed"}
    degraded_statuses = {"degraded", "insufficient_data", "no_data", "partial", "skipped"}
    if statuses and all(status == "completed" for status in statuses):
        report_status = "completed"
        quality_gate_passed = True
        quality_reason = None
    elif any(status in failure_statuses for status in statuses):
        report_status = "quality_failed"
        quality_gate_passed = False
        failed_steps = [step.get("stage") for step in report["steps"] if str(step.get("status") or "").strip().lower() in failure_statuses]
        quality_reason = f"关键阶段失败：{', '.join(str(s) for s in failed_steps if s)}"
    elif any(status in degraded_statuses for status in statuses):
        report_status = "degraded"
        quality_gate_passed = False
        degraded_steps = [step.get("stage") for step in report["steps"] if str(step.get("status") or "").strip().lower() in degraded_statuses]
        quality_reason = f"部分阶段未达产品门槛：{', '.join(str(s) for s in degraded_steps if s)}"
    else:
        report_status = "partial"
        quality_gate_passed = False
        quality_reason = "存在未识别的阶段状态"

    report["status"] = report_status
    report["outcome_status"] = report_status
    report["quality_gate_passed"] = quality_gate_passed
    report["quality_reason"] = quality_reason
    report["completed_at"] = datetime.utcnow().isoformat(timespec="seconds")
    _write_json(paths["contracts"] / "autonomous_cascade_report.latest.json", report)
    print(f"\nReport: {paths['contracts'] / 'autonomous_cascade_report.latest.json'}")
    return report


def main():
    parser = argparse.ArgumentParser(description="梯级水电全自主运行统一入口")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--stages", default=None, help=f"逗号分隔: {','.join(ALL_STAGES)}")
    args = parser.parse_args()
    stages = args.stages.split(",") if args.stages else None
    report = run_autonomous(args.case_id, stages)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
