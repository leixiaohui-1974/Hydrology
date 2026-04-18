#!/usr/bin/env bash
# Rollout 仓库契约一站式：必达路径 + JSON 形状 + 平台治理索引（check_rollout_repo_contracts.py）
# + 与 CI 相同的 5 文件 pytest 镜像（run_rollout_pytest_mirror.sh）。
# 须在 monorepo 仓库根下调用。
# CI / multi_model_iteration_verify 约定顺序：check_rollout_cases_loadable → 本脚本 → test_rollout_gates_case_ids_sync。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
python3 Hydrology/scripts/check_rollout_repo_contracts.py
bash Hydrology/scripts/run_rollout_pytest_mirror.sh
