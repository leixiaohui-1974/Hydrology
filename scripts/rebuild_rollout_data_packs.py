#!/usr/bin/env python3
"""
从各案例 `cases/<id>/manifest.yaml` 的 `latest_*` 路径重建 `data_pack.latest.json`。

- 调用 `workflows/build_data_pack.py`，默认带 `--relax-dem-outlet-validation`（e2e source_bundle 常无 DEM）。
- 若 `latest_source_bundle.path` 指向的文件不像 SourceBundle（无 `records` 列表），则跳过（如 yjdt 暂指 case_manifest）。

用法（仓库根）:
  python3 Hydrology/scripts/rebuild_rollout_data_packs.py --case-id jiaodongtiaoshui
  python3 Hydrology/scripts/rebuild_rollout_data_packs.py --all-rollout
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"
BUILD_SCRIPT = HYDROLOGY / "workflows" / "build_data_pack.py"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install pyyaml") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _looks_like_source_bundle(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("records"), list)


def _latest_path(data: dict[str, Any], key: str) -> Path | None:
    block = data.get(key)
    if not isinstance(block, dict):
        return None
    rel = (block.get("path") or "").strip()
    if not rel:
        return None
    return (WORKSPACE / rel).resolve()


def run_case(case_id: str, dry_run: bool) -> dict[str, Any]:
    cid = case_id.strip()
    man_path = WORKSPACE / "cases" / cid / "manifest.yaml"
    out: dict[str, Any] = {"case_id": cid, "status": "unknown"}
    if not man_path.is_file():
        out["status"] = "skip"
        out["reason"] = "manifest_missing"
        return out
    data = _load_yaml(man_path)
    sb = _latest_path(data, "latest_source_bundle")
    ou = _latest_path(data, "latest_outlets")
    cm = WORKSPACE / "cases" / cid / "contracts" / "case_manifest.json"
    dest = WORKSPACE / "cases" / cid / "contracts" / "data_pack.latest.json"
    if sb is None or ou is None or not cm.is_file():
        out["status"] = "skip"
        out["reason"] = "missing_paths"
        return out
    if not _looks_like_source_bundle(sb):
        out["status"] = "skip"
        out["reason"] = "source_bundle_not_contract"
        out["path"] = str(sb)
        return out
    cmd = [
        sys.executable,
        str(BUILD_SCRIPT),
        "--case-manifest",
        str(cm),
        "--source-bundle-json",
        str(sb),
        "--outlets-json",
        str(ou),
        "--output",
        str(dest),
        "--relax-dem-outlet-validation",
    ]
    out["cmd"] = cmd
    if dry_run:
        out["status"] = "dry_run"
        return out
    proc = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True)
    if proc.returncode != 0:
        out["status"] = "error"
        out["stderr"] = (proc.stderr or "")[-2000:]
        out["stdout"] = (proc.stdout or "")[-1000:]
        return out
    out["status"] = "ok"
    out["output"] = str(dest)
    return out


def _rollout_case_ids() -> list[str]:
    ids: list[str] = []
    for p in sorted((WORKSPACE / "cases").glob("*/manifest.yaml")):
        try:
            data = _load_yaml(p)
        except Exception:
            continue
        case = data.get("case") or {}
        if not isinstance(case, dict):
            continue
        if (case.get("priority") or "").strip() == "rollout":
            cid = (case.get("id") or p.parent.name).strip()
            if cid:
                ids.append(cid)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", action="append", dest="case_ids", default=[])
    ap.add_argument("--all-rollout", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not BUILD_SCRIPT.is_file():
        print("missing build_data_pack.py", file=sys.stderr)
        return 2
    ids = list(args.case_ids or [])
    if args.all_rollout:
        ids.extend(_rollout_case_ids())
    seen: set[str] = set()
    uniq = [x for x in ids if x.strip() and not (x.strip() in seen or seen.add(x.strip()))]
    if not uniq:
        print("no case ids", file=sys.stderr)
        return 2
    rows = [run_case(cid, args.dry_run) for cid in uniq]
    print(json.dumps({"cases": rows}, ensure_ascii=False, indent=2))
    if any(r.get("status") == "error" for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
