#!/usr/bin/env python3
"""
为缺 Run/Review/Release triad 与 **data_pack 指针** 的案例写入最小 canonical JSON（`_auto_generated`）。

- Triad：仅当 `{workflow_run,review_bundle,release_manifest}.json` 不存在时写入（可与 `.contract.json` 共存）。
- **data_pack**：仅当不存在 `data_pack.latest.json` / `data_pack.contract.json` / `data_pack.v2.json` / `data_pack.json` 任一时，写入 **`data_pack.latest.json`**（路径为**相对 workspace 根**的 POSIX 串）。
- 不替代正式 `build_data_pack` / `build-release-pack`；供契约存在性门禁与联调。

示例：
  python3 Hydrology/scripts/bootstrap_case_triad_minimal.py --dry-run --from-loop
  python3 Hydrology/scripts/bootstrap_case_triad_minimal.py --apply --case-id yjdt
  python3 Hydrology/scripts/bootstrap_case_triad_minimal.py --apply --from-loop
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
WORKSPACE = _SCRIPTS_DIR.parent.parent
_HYDROLOGY_ROOT = WORKSPACE / "Hydrology"
for _p in (_SCRIPTS_DIR, _HYDROLOGY_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from common.program_contract_outputs import default_governance_gates_ref_for_release  # noqa: E402
from hydrodesk_loop_yaml_util import load_loop_yaml, resolve_case_ids  # noqa: E402

DEFAULT_LOOP = WORKSPACE / "Hydrology" / "configs" / "hydrodesk_autonomous_waternet_e2e_loop.yaml"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def triad_json_absent(contracts: Path, base: str) -> bool:
    """`*.json` 本体缺失时返回 True；已有 `.contract.json` 不妨碍补写 triad `.json`。"""
    return not (contracts / f"{base}.json").is_file()


_DATA_PACK_CANDIDATES = (
    "data_pack.latest.json",
    "data_pack.contract.json",
    "data_pack.v2.json",
    "data_pack.json",
)


def data_pack_placeholder_absent(contracts: Path) -> bool:
    return not any((contracts / name).is_file() for name in _DATA_PACK_CANDIDATES)


def minimal_data_pack_payload(case_id: str) -> dict[str, Any]:
    ts = _iso_now()
    cm = f"cases/{case_id}/contracts/case_manifest.json"
    return {
        "kind": "data_pack",
        "schema_version": "0.1.0",
        "case_manifest": cm,
        "source_bundle_json": None,
        "outlets_json": None,
        "review_gates": {"basin_validation_json": None},
        "strict": False,
        "summary": {
            "_bootstrap": "minimal_data_pack_placeholder",
            "note": "Replace via build_data_pack / workflows when inputs are ready.",
        },
        "generated_at": ts,
        "_auto_generated": True,
        "_bootstrap": "minimal_data_pack_placeholder",
    }


def minimal_payloads(case_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """与 hydromind-contracts 校验及 rollout_hydrodesk_triad JSON 门禁对齐的最小占位。"""
    run_id = f"{case_id}-hydrodesk-triad-bootstrap"
    review_id = f"review-{case_id}-hydrodesk-triad-bootstrap"
    cm_rel = f"cases/{case_id}/contracts/case_manifest.json"
    ts = _iso_now()
    wf: dict[str, Any] = {
        "run_id": run_id,
        "case_id": case_id,
        "workflow_type": "hydrodesk_e2e",
        "status": "completed_with_review",
        "inputs": [
            {
                "artifact_id": f"{run_id}:case_manifest",
                "artifact_type": "config",
                "path": cm_rel,
                "metadata": {"role": "case_manifest_pointer"},
            }
        ],
        "outputs": [],
        "steps": [],
        "started_at": ts,
        "completed_at": ts,
        "metadata": {
            "components": ["hydrodesk_triad_bootstrap"],
            "dt_seconds": 0.0,
            "num_steps": 0,
            "_bootstrap": "minimal_triad_placeholder",
        },
        "schema_version": "0.1.0",
        "generated_at": ts,
        "_auto_generated": True,
        "_bootstrap": "minimal_triad_placeholder",
    }
    rb: dict[str, Any] = {
        "review_id": review_id,
        "run_id": run_id,
        "case_id": case_id,
        "verdict": "pending_review",
        "findings": [],
        "report_artifacts": [],
        "metadata": {"_bootstrap": "minimal_triad_placeholder"},
        "schema_version": "0.1.0",
        "generated_at": ts,
        "_auto_generated": True,
        "_bootstrap": "minimal_triad_placeholder",
    }
    ver = f"v0-bootstrap-{case_id}"
    rm: dict[str, Any] = {
        "release_id": f"release-{case_id}-hydrodesk-bootstrap",
        "case_id": case_id,
        "version": ver,
        "channel": "hydrodesk-shell",
        "governance_gates": default_governance_gates_ref_for_release(),
        "status": "review_pending",
        "included_runs": [run_id],
        "review_refs": [review_id],
        "artifacts": [],
        "metadata": {"_bootstrap": "minimal_triad_placeholder"},
        "schema_version": "0.1.0",
        "generated_at": ts,
        "_auto_generated": True,
        "_bootstrap": "minimal_triad_placeholder",
    }
    return wf, rb, rm


def run_for_case(case_id: str, apply: bool) -> dict[str, Any]:
    cid = case_id.strip()
    contracts = WORKSPACE / "cases" / cid / "contracts"
    out: dict[str, Any] = {"case_id": cid, "wrote": [], "skipped": [], "ok": True}
    if not contracts.is_dir():
        out["ok"] = False
        out["error"] = "contracts_directory_missing"
        return out
    wf, rb, rm = minimal_payloads(cid)
    payloads = {"workflow_run": wf, "review_bundle": rb, "release_manifest": rm}
    for base, obj in payloads.items():
        if not triad_json_absent(contracts, base):
            out["skipped"].append(base)
            continue
        path = contracts / f"{base}.json"
        rel = str(path.relative_to(WORKSPACE))
        if apply:
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out["wrote"].append(rel)

    if data_pack_placeholder_absent(contracts):
        dp_path = contracts / "data_pack.latest.json"
        rel_dp = str(dp_path.relative_to(WORKSPACE))
        if apply:
            dp_path.write_text(
                json.dumps(minimal_data_pack_payload(cid), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        out["wrote"].append(rel_dp)
    else:
        out["skipped"].append("data_pack")

    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Bootstrap minimal workflow/review/release triad JSON")
    p.add_argument("--case-id", action="append", default=[], help="可重复")
    p.add_argument("--from-loop", action="store_true", help="使用主闭环 YAML 的 case_selection")
    p.add_argument("--config", type=Path, default=DEFAULT_LOOP)
    p.add_argument("--apply", action="store_true", help="写入文件（默认仅打印计划）")
    args = p.parse_args()
    cfg_path = args.config if args.config.is_absolute() else WORKSPACE / args.config
    ids: list[str] = [str(x).strip() for x in (args.case_id or []) if str(x).strip()]
    if args.from_loop:
        cfg = load_loop_yaml(WORKSPACE, cfg_path.resolve())
        ids.extend(resolve_case_ids(cfg, WORKSPACE))
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    if not uniq:
        print(json.dumps({"ok": False, "error": "no_case_ids"}, ensure_ascii=False), file=sys.stderr)
        return 2
    rows = [run_for_case(cid, args.apply) for cid in uniq]
    print(json.dumps({"ok": all(r.get("ok") for r in rows), "apply": args.apply, "cases": rows}, ensure_ascii=False, indent=2))
    return 0 if all(r.get("ok") for r in rows) else 3


if __name__ == "__main__":
    raise SystemExit(main())
