#!/usr/bin/env python3
"""
HydroMind Case Config Generator
Enforces Zero-Hardcoding & relative paths.

Usage:
    python3 generate_case_config.py --case-id yinchuojiliao --name "引绰济辽" --stations "石棉,瀑布沟"
"""

import argparse
import sys
import yaml
from pathlib import Path

def generate_config(case_id: str, name: str, stations: list[str], output_dir: Path):
    """Generate a clean, relative-path based case configuration."""
    
    config = {
        "case_id": case_id,
        "display_name": name,
        "scan_dirs": [
            f"cases/{case_id}/data/raw",
            f"cases/{case_id}/data/knowledge"
        ],
        "target_stations": stations,
        "scan_extensions": [".json", ".csv", ".sqlite3", ".db", ".txt", ".xlsx"],
        
        "dem_path": f"cases/{case_id}/data/dem.tif",
        "river_network_path": f"cases/{case_id}/data/river_network.geojson",
        "source_bundle_path": f"cases/{case_id}/contracts/source_bundle.json",
        "case_manifest_path": f"cases/{case_id}/manifest.yaml",
        
        "topology_json_paths": [f"cases/{case_id}/data/topology.json"],
        "sqlite_paths": [f"cases/{case_id}/data/scada.sqlite3"],
        
        "output_dir": f"cases/{case_id}/contracts/outcomes",
        
        "validation": {
            "lat_range": [15.0, 55.0],
            "lon_range": [70.0, 140.0],
            "outlier_threshold_deg": 1.5,
            "min_precision_digits": 2
        },
        "modeling": {
            "delineation": {
                "snap_distance": 5000.0,
                "stream_threshold": 100.0
            },
            "hydrology": {
                "runoff_model": "xinanjiang",
                "routing_model": "muskingum",
                "dt_hours": 1.0,
                "simulation_hours": 720
            },
            "hydraulics": {
                "dt_seconds": 10,
                "manning_n": 0.035,
                "steady_state_max_iter": 5000,
                "steady_state_tolerance": 0.05
            }
        }
    }
    
    # Ensure directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create required data subdirectories
    (output_dir / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (output_dir / "data" / "knowledge").mkdir(parents=True, exist_ok=True)
    (output_dir / "contracts" / "outcomes").mkdir(parents=True, exist_ok=True)
    
    # Save YAML
    yaml_path = output_dir / f"{case_id}.yaml"
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
    print(f"✅ Case configuration generated at: {yaml_path}")
    print(f"✅ Data directories initialized at: {output_dir}/data")
    print(f"⚠️  Please place raw data inside {output_dir}/data/raw - DO NOT use absolute paths outside the workspace.")
    
def main():
    parser = argparse.ArgumentParser(description="Generate a purely relative case config")
    parser.add_argument("--case-id", required=True, help="Unique identifier, e.g., 'yjdt'")
    parser.add_argument("--name", required=True, help="Display name, e.g., '引江济淮'")
    parser.add_argument("--stations", default="", help="Comma separated target stations")
    parser.add_argument("--root-dir", default=".", help="Workspace root directory")
    
    args = parser.parse_args()
    
    stations = [s.strip() for s in args.stations.split(",")] if args.stations else []
    
    workspace = Path(args.root_dir).resolve()
    cases_dir = workspace / "cases" / args.case_id
    
    generate_config(args.case_id, args.name, stations, cases_dir)

if __name__ == "__main__":
    main()
