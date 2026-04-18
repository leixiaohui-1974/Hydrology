#!/usr/bin/env bash
# 与 hydrodesk-ci / pure-gate-ci 相同的 rollout + bootstrap triad pytest 镜像。
# 须在仓库根执行，或从任意目录：bash Hydrology/scripts/run_rollout_pytest_mirror.sh [extra pytest args]
# 依赖：pytest（requirements-ci.txt / hydrodesk-ci pip install）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HY="$REPO_ROOT/Hydrology"
cd "$REPO_ROOT"
exec python3 -m pytest -o addopts= -o log_cli=false -o filterwarnings=default \
  "$HY/tests/test_rollout_artifact_paths_exist.py" \
  "$HY/tests/test_rollout_json_shape_gates.py" \
  "$HY/tests/test_platform_governance_index.py" \
  "$HY/tests/test_bootstrap_triad_contract_alignment.py" \
  "$HY/tests/test_bootstrap_triad_json_absent.py" \
  -q \
  "$@"
