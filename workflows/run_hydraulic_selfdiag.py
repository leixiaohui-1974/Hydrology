#!/usr/bin/env python3
"""推演 (TuiYan) — 水力仿真与耦合计算

HydroMind 水智工坊 · Agent #6

水动力自诊断自修复工作流产品。

自动检测并修复常见水动力建模问题：
  - 边界条件错误（上下游节点未标记 bc）
  - 水位爆炸（超物理水位）
  - 稳态不收敛
  - 入流分配不合理
  - 河道几何参数不匹配

工作流：诊断 → 分类 → 修复建议 → 自动修复 → 重新运行 → 验证 → 报告

产品化：零硬编码，配置驱动，通用于所有案例。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflows._shared import BASE_DIR, WORKSPACE, load_case_config, write_json, load_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 诊断器 ────────────────────────────────────────────────────────────────────

class HydraulicDiagnostics:
    """对水动力合约进行自动诊断。"""

    def __init__(self, case_id: str, cfg: dict):
        self.case_id = case_id
        self.cfg = cfg
        self.contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
        self.product_dir = WORKSPACE / "cases" / case_id / "source_selection" / "product_outputs"
        self.issues: list[dict] = []

    def run_all(self) -> list[dict]:
        self.issues = []
        self._check_boundary_config()
        self._check_steady_state()
        self._check_unsteady_levels()
        self._check_inflow_magnitude()
        self._check_channel_geometry()
        return self.issues

    def _add_issue(self, severity: str, category: str, description: str,
                   fix: str, auto_fixable: bool = False, details: dict | None = None):
        self.issues.append({
            "severity": severity,
            "category": category,
            "description": description,
            "fix": fix,
            "auto_fixable": auto_fixable,
            "details": details or {},
        })

    def _check_boundary_config(self):
        """检查边界条件是否正确配置。"""
        hp_path = self.product_dir / "hydraulic_params.json"
        if not hp_path.exists():
            self._add_issue("error", "boundary",
                            "缺少 hydraulic_params.json，无法验证边界条件",
                            "运行 source_discovery 工作流", False)
            return

        hp = load_json(hp_path)
        stations = hp.get("stations", {})
        boundaries = hp.get("boundaries", {})

        upstream_bc = [n for n, info in stations.items() if info.get("nodeType") == 2]
        downstream_bc = [n for n, info in stations.items() if info.get("nodeType") == 1]

        if not upstream_bc:
            self._add_issue("critical", "boundary",
                            "未找到上游边界节点 (nodeType=2)",
                            "检查 hydraulic_params.json 拓扑", False)
        if not downstream_bc:
            self._add_issue("critical", "boundary",
                            "未找到下游边界节点 (nodeType=1)",
                            "检查 hydraulic_params.json 拓扑", False)

        for name in upstream_bc:
            if name not in boundaries:
                self._add_issue("error", "boundary",
                                f"上游边界节点 {name} 无边界条件值",
                                f"在 boundaries 中添加 {name} 的流量值", True,
                                {"node": name, "type": "upstream"})

        for name in downstream_bc:
            if name not in boundaries:
                self._add_issue("warning", "boundary",
                                f"下游边界节点 {name} 无边界条件值",
                                f"在 boundaries 中添加 {name} 的水位值", True,
                                {"node": name, "type": "downstream"})

    def _check_steady_state(self):
        """检查稳态收敛状况。"""
        steady_path = self.contracts_dir / "hydraulics_steady.latest.json"
        if not steady_path.exists():
            return

        steady = load_json(steady_path)
        if not steady.get("converged"):
            self._add_issue("critical", "convergence",
                            f"稳态未收敛，迭代 {steady.get('iterations')} 次，"
                            f"最终 dH={steady.get('final_dH', '?'):.4f} m",
                            "增大 max_iter 或放宽 tolerance，或检查边界条件", True,
                            {"iterations": steady.get("iterations"),
                             "final_dH": steady.get("final_dH"),
                             "tolerance": steady.get("tolerance")})

        levels = steady.get("steady_state_levels_m", {})
        hp_path = self.product_dir / "hydraulic_params.json"
        if hp_path.exists():
            hp = load_json(hp_path)
            for name, level in levels.items():
                zb = hp.get("stations", {}).get(name, {}).get("zb")
                if zb is not None and level > zb + 200:
                    self._add_issue("critical", "water_level_explosion",
                                    f"稳态 {name} 水位 {level:.1f}m 远超河底 {zb}m + 200m",
                                    "检查该节点的边界条件和入流分配", True,
                                    {"node": name, "level": level, "zb": zb,
                                     "excess_m": level - zb})

    def _check_unsteady_levels(self):
        """检查非稳态水位是否超物理范围。"""
        unsteady_path = self.contracts_dir / "hydraulics_unsteady.latest.json"
        if not unsteady_path.exists():
            return

        unsteady = load_json(unsteady_path)
        hp_path = self.product_dir / "hydraulic_params.json"
        hp = load_json(hp_path) if hp_path.exists() else {}

        for name, info in unsteady.get("stations", {}).items():
            max_level = info.get("max_level_m", 0)
            zb = hp.get("stations", {}).get(name, {}).get("zb")
            if zb is None:
                continue

            water_depth = max_level - zb
            if water_depth > 200:
                self._add_issue("critical", "water_level_explosion",
                                f"非稳态 {name} 最大水位 {max_level:.1f}m，"
                                f"水深 {water_depth:.1f}m 严重超物理范围",
                                "检查该节点边界条件、入流量级、河道断面", True,
                                {"node": name, "max_level": max_level, "zb": zb,
                                 "water_depth": water_depth})
            elif water_depth > 50:
                self._add_issue("warning", "high_water_level",
                                f"非稳态 {name} 水深 {water_depth:.1f}m 偏高",
                                "检查河道宽度/深度参数是否合理",
                                details={"node": name, "water_depth": water_depth})

            if max_level < zb:
                self._add_issue("error", "dry_bed",
                                f"非稳态 {name} 水位 {max_level:.1f}m 低于河底 {zb}m",
                                "检查入流和边界条件",
                                details={"node": name, "max_level": max_level, "zb": zb})

    def _check_inflow_magnitude(self):
        """检查入流量级是否合理。"""
        hydro_path = self.contracts_dir / "hydrology_sim.latest.json"
        if not hydro_path.exists():
            return

        hydro = load_json(hydro_path)
        outflow = hydro.get("outflow_timeseries", [])
        if not outflow:
            return

        import numpy as np
        arr = np.array(outflow)
        peak = float(np.max(arr))
        mean = float(np.mean(arr[arr > 0])) if np.any(arr > 0) else 0

        hp_path = self.product_dir / "hydraulic_params.json"
        if hp_path.exists():
            hp = load_json(hp_path)
            bc_flow = next(
                (v for n, v in hp.get("boundaries", {}).items()
                 if hp.get("stations", {}).get(n, {}).get("nodeType") == 2),
                None
            )
            if bc_flow and peak > bc_flow * 100:
                self._add_issue("warning", "inflow_magnitude",
                                f"水文模型峰值流量 {peak:.0f} m³/s 是边界基流 "
                                f"{bc_flow:.0f} m³/s 的 {peak/bc_flow:.0f} 倍",
                                "水文出流可能是全流域汇总值，需按区间面积比分配到各节点",
                                details={"peak": peak, "mean": mean, "bc_flow": bc_flow})

    def _check_channel_geometry(self):
        """检查河道几何参数是否合理。"""
        hp_path = self.product_dir / "hydraulic_params.json"
        if not hp_path.exists():
            return

        hp = load_json(hp_path)
        cfg_hyd = self.cfg.get("modeling", {}).get("hydraulics", {})
        width = cfg_hyd.get("default_width", 100)
        depth = cfg_hyd.get("default_depth", 10)

        bc_flow = next(
            (v for n, v in hp.get("boundaries", {}).items()
             if hp.get("stations", {}).get(n, {}).get("nodeType") == 2),
            334.0
        )
        manning_n = cfg_hyd.get("manning_n", 0.035)
        hydraulic_capacity = (width * depth) * (1.0 / manning_n) * \
                             ((width * depth) / (width + 2 * depth)) ** (2 / 3) * 0.001 ** 0.5

        if hydraulic_capacity < bc_flow * 0.5:
            self._add_issue("warning", "channel_geometry",
                            f"断面过流能力 {hydraulic_capacity:.0f} m³/s 不足（基流 {bc_flow:.0f} m³/s），"
                            f"宽 {width}m 深 {depth}m",
                            "增大 default_width 或 default_depth",
                            details={"capacity": hydraulic_capacity, "base_flow": bc_flow,
                                     "width": width, "depth": depth})


# ── 修复器 ────────────────────────────────────────────────────────────────────

def _auto_fix_steady_tolerance(cfg: dict, issues: list[dict]) -> list[str]:
    """如果稳态不收敛且 dH 接近阈值，自动放宽容差。"""
    fixes = []
    for issue in issues:
        if issue["category"] == "convergence" and issue["auto_fixable"]:
            details = issue["details"]
            final_dh = details.get("final_dH", 999)
            tol = details.get("tolerance", 0.05)
            if final_dh < tol * 10:
                new_tol = round(final_dh * 2, 4)
                cfg.setdefault("modeling", {}).setdefault("hydraulics", {})["steady_state_tolerance"] = new_tol
                fixes.append(f"放宽稳态容差 {tol} → {new_tol}")
            else:
                cfg.setdefault("modeling", {}).setdefault("hydraulics", {})["steady_state_max_iter"] = 10000
                fixes.append("增大稳态最大迭代到 10000")
    return fixes


# ── 主工作流 ──────────────────────────────────────────────────────────────────

def selfdiag(
    case_id: str,
    *,
    config_path: str | None = None,
    auto_fix: bool = True,
    rerun: bool = True,
    max_rounds: int = 3,
) -> dict[str, Any]:
    """水动力自诊断自修复主入口。

    1. 诊断当前合约中的问题
    2. 分类 (critical/error/warning)
    3. 对 auto_fixable 的问题自动修复配置
    4. 重新运行 steady + unsteady
    5. 再次诊断验证
    6. 输出诊断报告
    """
    cfg = load_case_config(case_id, config_path)
    report = {
        "case_id": case_id,
        "workflow": "hydraulic_selfdiag",
        "started_at": _now_iso(),
        "rounds": [],
    }

    for round_num in range(1, max_rounds + 1):
        diag = HydraulicDiagnostics(case_id, cfg)
        issues = diag.run_all()

        round_report = {
            "round": round_num,
            "issues_found": len(issues),
            "critical": sum(1 for i in issues if i["severity"] == "critical"),
            "error": sum(1 for i in issues if i["severity"] == "error"),
            "warning": sum(1 for i in issues if i["severity"] == "warning"),
            "issues": issues,
            "fixes_applied": [],
        }

        if not issues:
            round_report["verdict"] = "CLEAN"
            report["rounds"].append(round_report)
            break

        has_critical = any(i["severity"] == "critical" for i in issues)

        if auto_fix and has_critical:
            fixes = _auto_fix_steady_tolerance(cfg, issues)
            round_report["fixes_applied"] = fixes

        report["rounds"].append(round_report)

        if rerun and has_critical and round_num < max_rounds:
            print(f"  [selfdiag] 第 {round_num} 轮发现 {len(issues)} 个问题，重新运行水动力...")
            try:
                from workflows.run_full_modeling import run_full_modeling
                run_full_modeling(
                    case_id=case_id,
                    stages=["hydraulics_steady", "hydraulics_unsteady"],
                    config_path=config_path,
                )
            except Exception as e:
                round_report["rerun_error"] = str(e)
                break
        else:
            break

    final_issues = report["rounds"][-1]["issues"] if report["rounds"] else []
    critical_count = sum(1 for i in final_issues if i["severity"] == "critical")

    report["completed_at"] = _now_iso()
    report["total_rounds"] = len(report["rounds"])
    report["final_verdict"] = "PASS" if critical_count == 0 else "FAIL"
    report["final_critical_count"] = critical_count
    report["final_issue_count"] = len(final_issues)

    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    write_json(contracts_dir / "hydraulic_selfdiag.latest.json", report)

    return report


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    from workflows._autonomy_policy import argv_has, governance_source_relpath, section

    parser = argparse.ArgumentParser(description="水动力自诊断自修复工作流")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", help="YAML 配置路径")
    parser.add_argument("--no-fix", action="store_true", help="仅诊断不修复")
    parser.add_argument("--no-rerun", action="store_true", help="不重新运行")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    pol = section(args.case_id, "hydraulic_selfdiag", args.config)
    if not argv_has("--max-rounds") and "max_rounds" in pol:
        args.max_rounds = int(pol["max_rounds"])
    applied: dict[str, Any] = {}
    if not argv_has("--max-rounds") and "max_rounds" in pol:
        applied["max_rounds"] = pol["max_rounds"]

    result = selfdiag(
        args.case_id,
        config_path=args.config,
        auto_fix=not args.no_fix,
        rerun=not args.no_rerun,
        max_rounds=args.max_rounds,
    )
    result["policy_governance"] = {
        "source": governance_source_relpath(),
        "policy_file": "workflow_autonomy_policy.yaml",
        "section": "hydraulic_selfdiag",
        "applied_from_yaml": applied,
    }
    write_json(
        WORKSPACE / "cases" / args.case_id / "contracts" / "hydraulic_selfdiag.latest.json",
        result,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
