import sys
from pathlib import Path
import subprocess
import argparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def run_command(cmd):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run generic E2E dispatch/control validation for a case.")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    case_id = str(args.case_id).strip()
    python_bin = sys.executable
    
    # 1. Update YAML
    run_command([python_bin, "Hydrology/workflows/update_case_control_yaml.py", "--case-id", case_id])
    
    # 2. Predictive Scheduling
    run_command([python_bin, "Hydrology/workflows/run_predictive_scheduling.py", "--case-id", case_id])
    
    # 3. Realtime Control (ODD/SIL)
    run_command([python_bin, "Hydrology/workflows/run_realtime_control.py", "--case-id", case_id])
    
    # 4. WNAL Evaluation
    run_command([python_bin, "Hydrology/workflows/evaluate_simulation_accuracy.py", "--case-id", case_id, "--wnal-e2e"])
    
    print(f"E2E dispatch and control validation successful for {case_id}.")
