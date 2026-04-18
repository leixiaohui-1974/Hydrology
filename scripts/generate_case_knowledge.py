#!/usr/bin/env python3
"""Generate knowledge.latest.json for cases that lack it.

Reads case manifest (project_type) and data_pack (assets) to produce a
minimal knowledge contract with network_type, enabling run_full_modeling.py
smart routing for canal vs watershed cases.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
CASES_DIR = WORKSPACE / "cases"

PROJECT_TYPE_TO_NETWORK: dict[str, str] = {
    "canal": "open_channel_transfer",
    "pump_canal": "open_channel_transfer",
    "watershed": "natural_river",
}


def _load_json(p: Path) -> dict:
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_yaml(p: Path) -> dict:
    if not p.is_file():
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except ImportError:
        return {}


def generate_knowledge(case_id: str) -> dict:
    case_dir = CASES_DIR / case_id
    contracts = case_dir / "contracts"

    manifest = _load_json(contracts / "case_manifest.json")
    data_pack = _load_json(contracts / "data_pack.latest.json")
    manifest_yaml = _load_yaml(case_dir / "manifest.yaml")

    project_type = (
        manifest.get("project_type")
        or manifest_yaml.get("project_type")
        or "watershed"
    )
    network_type = PROJECT_TYPE_TO_NETWORK.get(project_type, "natural_river")

    # Build assets list from data_pack
    assets = []
    assets.append({
        "asset_type": "topology",
        "payload": {
            "network_type": network_type,
            "project_type": project_type,
            "nodes": [],
        },
    })

    # DEM asset
    dem_path = data_pack.get("dem_path") or data_pack.get("dem_file")
    if dem_path:
        assets.append({"asset_type": "dem", "path": dem_path})

    # Outlet info
    outlet_count = data_pack.get("outlet_count", 0)
    if outlet_count:
        assets.append({
            "asset_type": "outlets",
            "count": outlet_count,
        })

    return {
        "case_id": case_id,
        "contract_type": "knowledge",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_type": project_type,
        "network_type": network_type,
        "assets": assets,
        "source_contracts": [
            f"cases/{case_id}/contracts/case_manifest.json",
            f"cases/{case_id}/contracts/data_pack.latest.json",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate knowledge.latest.json for cases")
    parser.add_argument("--case-id", help="Single case to generate (default: all missing)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing")
    args = parser.parse_args()

    case_ids = [args.case_id] if args.case_id else [
        d.name for d in sorted(CASES_DIR.iterdir())
        if d.is_dir() and (d / "contracts").is_dir()
    ]

    for cid in case_ids:
        out = CASES_DIR / cid / "contracts" / "knowledge.latest.json"
        if out.exists() and not args.force:
            print(f"SKIP {cid}: knowledge.latest.json already exists (use --force)")
            continue
        knowledge = generate_knowledge(cid)
        out.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"WROTE {cid}: {out} (network_type={knowledge['network_type']})")


if __name__ == "__main__":
    main()
