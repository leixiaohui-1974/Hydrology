"""
批量控制工作流执行网关 (Unified Control Workflow Batch Execution)
按顺序为所有有效案例（或指定案例）调用：
1. 状态估计 (D4) - run_state_estimation.py
2. 计划报电网 (D5 预测调度) - run_grid_dispatch.py
3. 软件在环控制测试 (D5/D6 SIL) - run_sil_testing.py
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Hydrology.workflows._shared import load_case_config, WORKSPACE

def run_cmd(cmd: list[str], cwd: Path) -> bool:
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [错误] 命令执行失败: {' '.join(cmd)}\n  {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="批量控制工作流执行网关")
    parser.add_argument("--case-id", help="指定要运行的案例 ID")
    parser.add_argument("--all", action="store_true", help="运行所有配置目录下的案例")
    args = parser.parse_args()

    if not args.case_id and not args.all:
        parser.error("必须指定 --case-id 或 --all")

    cases_to_run = []
    if args.all:
        configs_dir = WORKSPACE / "Hydrology" / "configs"
        for f in configs_dir.glob("*.yaml"):
            cases_to_run.append(f.stem)
    else:
        cases_to_run.append(args.case_id)

    print("=" * 60)
    print(" 🚀 统一控制工作流网关 (D4 State Estimation + D5/D6 SIL)")
    print("=" * 60)

    success_count = 0
    for cid in cases_to_run:
        print(f"\n[{cid}] 开始执行控制工作流...")
        cfg = load_case_config(cid)
        
        # 1. 运行状态估计 (D4)
        print(f"  --> 阶段 1: 状态估计 (D4) 与 Mock Sensor 注入")
        cmd_d4 = [
            sys.executable,
            "-m", "workflows.run_state_estimation",
            "--case-id", cid,
            "--use-mock-sensor"
        ]
        d4_ok = run_cmd(cmd_d4, cwd=WORKSPACE / "Hydrology")
        
        # 2. 运行计划报电网 (D5)
        print(f"  --> 阶段 2: 计划报电网与发电预测 (D5)")
        cmd_d5 = [
            sys.executable,
            "-m", "workflows.run_grid_dispatch",
            "--case-id", cid
        ]
        d5_ok = run_cmd(cmd_d5, cwd=WORKSPACE / "Hydrology")
        
        # 3. 运行 SIL 测试 (D5/D6)
        print(f"  --> 阶段 3: 软件在环控制测试 (D5/D6 SIL)")
        cmd_sil = [
            sys.executable,
            "-m", "workflows.run_sil_testing",
            "--case-id", cid
        ]
        sil_ok = run_cmd(cmd_sil, cwd=WORKSPACE / "Hydrology")
        
        if d4_ok and d5_ok and sil_ok:
            success_count += 1
            print(f"[{cid}] ✅ 控制工作流全部执行成功！")
        else:
            print(f"[{cid}] ❌ 控制工作流部分失败。")

    print("\n" + "=" * 60)
    print(f"执行完毕。共测试 {len(cases_to_run)} 个案例，完全成功 {success_count} 个。")
    print("生成的标准对象报告存放在: cases/<case_id>/contracts/object_reports/")
    print("=" * 60)

if __name__ == "__main__":
    main()
