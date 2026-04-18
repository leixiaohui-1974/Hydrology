#!/usr/bin/env python3
"""筑模 (ZhuMo) — 模型构建与拓扑组装

HydroMind 水智工坊 · Agent #4

Modular deterministic modeling workflows — independently usable, freely composable.

Architecture:
  Each workflow is a standalone stage that reads contract JSON and writes contract JSON.
  Stages can run independently or be chained via the orchestrator.

Workflow catalog:
  1. source_discovery     — knowledge mining + reliability scoring + parameter discovery
  2. data_pack            — DEM + outlet compatibility validation
  3. delineation          — WhiteboxTools watershed delineation
  4. hydrology            — rainfall-runoff + routing (Hydrology engine, independent)
  5. hydraulics_steady    — 1D SuperLink steady-state convergence (MUST pass before unsteady)
  6. hydraulics_unsteady  — 1D SuperLink unsteady simulation
  7. coupled              — hydrology-hydraulics coupled simulation

Modeling modes:
  --stages hydrology                  # independent hydrology only
  --stages hydraulics_steady          # steady-state convergence check only
  --stages hydraulics_steady,hydraulics_unsteady  # hydraulics pipeline
  --stages hydrology,coupled          # hydrology then coupling
  --stages all                        # full chain (default)

Design principles:
  - ALL logic is deterministic (no AI/LLM in any stage)
  - Same inputs → same outputs, always
  - Each stage reads from cases/{case_id}/contracts/*.json
  - Each stage writes to cases/{case_id}/contracts/*.json
  - No case-specific code — everything parameterized by case_id + config YAML

Usage:
    python3 run_full_modeling.py --case-id zhongxian
    python3 run_full_modeling.py --case-id zhongxian --stages hydrology
    python3 run_full_modeling.py --case-id zhongxian --stages hydraulics_steady,hydraulics_unsteady
    python3 run_full_modeling.py --case-id zhongxian --config configs/<case>_sim.yaml
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ── Utilities ────────────────────────────────────────────────────────────────

def _first_boundary_val(boundaries: dict, default: float = 334.0) -> float:
    """取边界条件第一个值（上游入流）。通用。"""
    return float(next(iter(boundaries.values()))) if boundaries else default


def _resolve_pipedream_path(workspace: Path) -> Path:
    """自动查找 pipedream 项目路径。不硬编码目录名。"""
    for candidate in ["pipedream-hydrology-integration-lab", "pipedream", "pipedream_solver"]:
        p = workspace / candidate
        if p.exists():
            return p
    return workspace / "pipedream-hydrology-integration-lab"


def _resolve_bundle_artifact_path(raw: str | None) -> Path:
    """source_bundle 内 artifact.path：相对路径一律相对 workspace root。"""
    if not raw:
        return Path()
    p = Path(raw)
    return p if p.is_absolute() else (WORKSPACE / p)


def _resolve_dem_from_source_bundle(source_bundle: dict[str, Any]) -> Path | None:
    for role in ("dem_authoritative", "dem_primary", "dem_cropped_tif", "dem_fallback"):
        for rec in source_bundle.get("records", []):
            if rec.get("role") == role:
                p = _resolve_bundle_artifact_path(rec.get("artifact", {}).get("path"))
                if p.exists():
                    return p
    return None


def _source_bundle_has_cross_sections(source_bundle: dict[str, Any]) -> bool:
    for rec in source_bundle.get("records", []):
        role = str(rec.get("role") or "").lower()
        role_in_bundle = str(rec.get("artifact", {}).get("metadata", {}).get("role_in_bundle") or "").lower()
        if "cross_section" not in role and "cross_section" not in role_in_bundle:
            continue
        path = _resolve_bundle_artifact_path(rec.get("artifact", {}).get("path"))
        if path.exists():
            return True
    return False


def _hydraulic_params_have_cross_sections(payload: dict[str, Any]) -> bool:
    sections_count = payload.get("sections_count")
    if isinstance(sections_count, (int, float)) and sections_count > 0:
        return True

    channels = payload.get("channels")
    if not isinstance(channels, list):
        return False

    for channel in channels:
        sec_names = channel.get("sec_names")
        if isinstance(sec_names, list) and len(sec_names) > 0:
            return True
        section_count = channel.get("section_count")
        if isinstance(section_count, (int, float)) and section_count > 0:
            return True
    return False


def _resolve_source_bundle_path(case_dir: Path, case_id: str) -> Path:
    """优先选择包含可用 DEM 的 authoritative bundle，否则回退到现有 contract。"""
    piped = (
        _resolve_pipedream_path(WORKSPACE)
        / "research"
        / "e2e_reports"
        / case_id
        / "contracts"
        / "source_bundle.contract.json"
    )
    case_bundle = case_dir / "contracts" / "source_bundle.contract.json"
    candidate_paths = [piped, case_bundle]

    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            if _resolve_dem_from_source_bundle(_load_json(path)) is not None:
                return path
        except Exception:
            continue

    for path in candidate_paths:
        if path.exists():
            return path
    return case_bundle


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _merge_config(user_cfg: dict, defaults: dict) -> dict:
    merged = dict(defaults)
    for key, val in user_cfg.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(val, merged[key])
        else:
            merged[key] = val
    return merged


# ── Default Config ───────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "delineation": {
        "snap_distance": 5000.0,
        "stream_threshold": 100.0,
    },
    "hydrology": {
        "runoff_model": "xinanjiang",
        "routing_model": "muskingum",
        "dt_hours": 1.0,
        "simulation_hours": 720,
        "runoff_params": {},
        "routing_params": {"K": 3.0, "x": 0.2},
    },
    "hydraulics": {
        "dt_seconds": 10,
        "steady_state_max_iter": 5000,
        "steady_state_tolerance": 0.05,
        "simulation_hours": 720,
        "manning_n": 0.035,
        "default_shape": "rect_open",
        "default_width": 300.0,
        "default_depth": 20.0,
        "internal_links": 4,
    },
}


# ── Generic Path Resolution ─────────────────────────────────────────────────

def resolve_paths(case_id: str) -> dict[str, Path]:
    case_dir = WORKSPACE / "cases" / case_id
    return {
        "case_dir": case_dir,
        "contracts": case_dir / "contracts",
        "pipeline_script": case_dir / "source_selection" / "product" / "pipeline.py",
        "product_outputs": case_dir / "source_selection" / "product_outputs",
        "case_manifest": case_dir / "contracts" / "case_manifest.json",
        "source_bundle": _resolve_source_bundle_path(case_dir, case_id),
    }


def _resolve_dem(paths: dict[str, Path]) -> str:
    source_bundle = _load_json(paths["source_bundle"])
    dem_path = _resolve_dem_from_source_bundle(source_bundle)
    if dem_path is not None:
        return str(dem_path)
    raise FileNotFoundError("No DEM found in source bundle")


# ── Stage 1: Source Discovery ────────────────────────────────────────────────

REQUIRED_SOURCE_DISCOVERY_OUTPUTS = {
    "outlets_delineation_ready": "outlets.delineation_ready.json",
    "control_station_mapping": "control_station_mapping.json",
    "source_reliability": "source_reliability.json",
    "coordinate_validation": "coordinate_validation.json",
}
NO_DELINEATION_READY_OUTLETS_REASON = "No delineation-ready outlets"
NO_DELINEATION_READY_OUTLETS_REASON_CODE = "no_delineation_ready_outlets"
OPEN_CHANNEL_TRANSFER_NO_RESERVOIR_REASON = "Network type is open_channel_transfer and no reservoir nodes found"
OPEN_CHANNEL_TRANSFER_NO_RESERVOIR_REASON_CODE = "open_channel_transfer_no_reservoir_nodes"
MISSING_CROSS_SECTION_REASON = "Missing Cross-Section data"
MISSING_CROSS_SECTION_REASON_CODE = "missing_cross_section_data"
D1_OR_D2_SKIPPED_REASON = "D1 or D2 skipped"
D1_OR_D2_SKIPPED_REASON_CODE = "d1_or_d2_skipped"


def _collect_existing_source_discovery_outputs(paths: dict[str, Path]) -> dict[str, str]:
    product_outputs = paths["product_outputs"]
    return {
        key: str(product_outputs / filename)
        for key, filename in REQUIRED_SOURCE_DISCOVERY_OUTPUTS.items()
        if (product_outputs / filename).exists()
    }


def _load_source_discovery_ready(ready_path: Path) -> tuple[dict[str, Any], int]:
    ready = _load_json(ready_path)
    outlet_count = int(ready.get("count", len(ready.get("outlets") or [])))
    return ready, outlet_count


def _build_source_discovery_result(
    *,
    mode: str,
    pipeline_present: bool,
    outlet_count: int,
    outputs: dict[str, str],
) -> dict[str, Any]:
    result = {
        "stage": "source_discovery",
        "status": "completed" if outlet_count > 0 else "insufficient_data",
        "mode": mode,
        "pipeline_present": pipeline_present,
        "outlet_count": outlet_count,
        "outputs": outputs,
    }
    if outlet_count <= 0:
        result["reason"] = NO_DELINEATION_READY_OUTLETS_REASON
        result["reason_code"] = NO_DELINEATION_READY_OUTLETS_REASON_CODE
    return result


def _require_complete_source_discovery_cache(paths: dict[str, Path]) -> dict[str, str]:
    outputs = _collect_existing_source_discovery_outputs(paths)
    missing_keys = sorted(set(REQUIRED_SOURCE_DISCOVERY_OUTPUTS) - set(outputs))
    if missing_keys:
        raise FileNotFoundError(
            "Pipeline not found and cached source_discovery outputs are incomplete: "
            + ", ".join(missing_keys)
        )
    return outputs


def run_source_discovery(paths: dict[str, Path]) -> dict[str, Any]:
    pipeline = paths["pipeline_script"]
    ready_path = paths["product_outputs"] / "outlets.delineation_ready.json"
    if not pipeline.exists():
        if not ready_path.exists():
            raise FileNotFoundError(f"Pipeline not found: {pipeline}")
        outputs = _require_complete_source_discovery_cache(paths)
        _, outlet_count = _load_source_discovery_ready(ready_path)
        return _build_source_discovery_result(
            mode="reused_existing_outputs",
            pipeline_present=False,
            outlet_count=outlet_count,
            outputs=outputs,
        )
    result = subprocess.run(
        [sys.executable, str(pipeline), "run-all"],
        capture_output=True, text=True, cwd=str(pipeline.parent),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Source discovery failed:\n{result.stderr}")
    _, outlet_count = _load_source_discovery_ready(ready_path)
    return _build_source_discovery_result(
        mode="pipeline",
        pipeline_present=True,
        outlet_count=outlet_count,
        outputs=_collect_existing_source_discovery_outputs(paths),
    )


# ── Stage 2: Data Pack ───────────────────────────────────────────────────────

def run_data_pack(paths: dict[str, Path]) -> dict[str, Any]:
    outlets_json = paths["product_outputs"] / "outlets.delineation_ready.json"
    output_path = paths["contracts"] / "data_pack.latest.json"
    _, outlet_count = _load_source_discovery_ready(outlets_json)
    if outlet_count <= 0:
        return {
            "stage": "data_pack",
            "status": "insufficient_data",
            "reason": NO_DELINEATION_READY_OUTLETS_REASON,
            "reason_code": NO_DELINEATION_READY_OUTLETS_REASON_CODE,
            "outlet_count": 0,
        }
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "workflows" / "build_data_pack.py"),
         "--case-manifest", str(paths["case_manifest"]),
         "--source-bundle-json", str(paths["source_bundle"]),
         "--outlets-json", str(outlets_json),
         "--output", str(output_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Data pack failed:\n{result.stderr}")
    pack = _load_json(output_path)
    v = pack["summary"]["dem_outlet_validation"]
    return {"stage": "data_pack", "status": "completed", "all_in_dem": v["all_outlets_within_dem"]}


# ── Stage 3: Delineation ─────────────────────────────────────────────────────

def run_delineation(paths: dict[str, Path], cfg: dict) -> dict[str, Any]:
    from hydro_model.whitebox_delineation import run_whitebox_watershed_delineation
    outlets_data = _load_json(paths["product_outputs"] / "outlets.delineation_ready.json")
    outlets = [{"name": o["name"], "lat": o["lat"], "lon": o["lon"]} for o in outlets_data["outlets"]]
    result = run_whitebox_watershed_delineation(
        dem_path=_resolve_dem(paths), outlets=outlets, subtract_upstream=True,
        stream_threshold=cfg["stream_threshold"], snap_distance=cfg["snap_distance"],
    )
    _write_json(paths["contracts"] / "delineation.latest.json", result)
    return {
        "stage": "delineation", "status": "completed",
        "total_area_km2": result["total_area_km2"],
        "basins": [{"name": b["name"], "area_km2": round(b["area_km2"], 1)}
                   for b in sorted(result["basins"], key=lambda x: -x["area_km2"])],
    }


# ── Stage 4: Hydrology (independent) ────────────────────────────────────────

def _make_runoff(name: str, params: dict) -> Any:
    from hydro_model.runoff import (
        SimpleRunoffModule, SCSCurveNumberModule, XinanjiangRunoffModule,
        HymodRunoffModule, HortonRunoffModule,
    )
    return {"simple": SimpleRunoffModule, "scs": SCSCurveNumberModule,
            "xinanjiang": XinanjiangRunoffModule, "hymod": HymodRunoffModule,
            "horton": HortonRunoffModule}[name.lower()](**params)


def _make_routing(name: str, params: dict) -> Any:
    from hydro_model.routing import (
        SimpleRouting, MuskingumRouting, UnitHydrographRouting, MuskingumCungeRouting,
    )
    return {"simple": SimpleRouting, "muskingum": MuskingumRouting,
            "unit_hydrograph": UnitHydrographRouting,
            "muskingum_cunge": MuskingumCungeRouting}[name.lower()](**params)


def run_hydrology(paths: dict[str, Path], cfg: dict) -> dict[str, Any]:
    """Independent rainfall-runoff simulation. No hydraulics dependency."""
    delin = _load_json(paths["contracts"] / "delineation.latest.json")
    basins = sorted(delin["basins"], key=lambda b: -b["area_km2"])

    # Load rainfall from source bundle
    source_bundle = _load_json(paths["source_bundle"])
    rain_path = None
    for rec in source_bundle.get("records", []):
        if rec.get("role") == "rainfall_timeseries":
            p = _resolve_bundle_artifact_path(rec.get("artifact", {}).get("path"))
            if p.exists():
                rain_path = p
                break

    dt_h = cfg["dt_hours"]
    n_steps = int(cfg["simulation_hours"] / dt_h)

    if rain_path and rain_path.exists():
        import pandas as pd
        rain_df = pd.read_csv(rain_path)
        numeric_cols = rain_df.select_dtypes(include=[np.number]).columns
        rain_series = rain_df[numeric_cols[0]].values[:n_steps] if len(numeric_cols) > 0 else np.zeros(n_steps)
    else:
        rain_series = np.zeros(n_steps)
        rain_series[min(24, n_steps):min(30, n_steps)] = 20.0

    if len(rain_series) < n_steps:
        rain_series = np.pad(rain_series, (0, n_steps - len(rain_series)))

    basin_results = []
    total_outflow = np.zeros(n_steps)

    for basin in basins:
        runoff = _make_runoff(cfg["runoff_model"], cfg.get("runoff_params", {}))
        routing = _make_routing(cfg["routing_model"], cfg.get("routing_params", {}))
        outflow_series = np.zeros(n_steps)
        total_runoff = 0.0

        for t in range(n_steps):
            r = runoff.run(float(rain_series[t]), 0.0)
            total_runoff += r
            q = r * basin["area_km2"] * 1e6 / (dt_h * 3600 * 1000)
            outflow_series[t] = routing.run(q)

        total_outflow += outflow_series
        basin_results.append({
            "name": basin["name"], "area_km2": basin["area_km2"],
            "total_runoff_mm": float(total_runoff),
            "peak_flow_m3s": float(np.max(outflow_series)),
            "peak_time_h": float(np.argmax(outflow_series)) * dt_h,
        })

    result = {
        "config": cfg, "basins": basin_results,
        "total_peak_m3s": float(np.max(total_outflow)),
        "total_peak_time_h": float(np.argmax(total_outflow) * dt_h),
        "outflow_timeseries": total_outflow.tolist(),
    }
    _write_json(paths["contracts"] / "hydrology_sim.latest.json", result)
    return {"stage": "hydrology", "status": "completed",
            "basins": len(basin_results), "total_peak_m3s": result["total_peak_m3s"]}


# ── Stage 5: Hydraulics Steady State ─────────────────────────────────────────

def _build_superlink_network(paths: dict[str, Path], cfg: dict) -> Any:
    """Build SuperLink model from discovered parameters. Deterministic."""
    import pandas as pd
    # Ensure Hydrology's hydro_model is on path BEFORE pipedream
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    pipedream_path = str(_resolve_pipedream_path(WORKSPACE))
    if pipedream_path not in sys.path:
        sys.path.append(pipedream_path)  # append, not insert, so Hydrology takes priority
    from pipedream_solver.superlink import SuperLink

    # Use hydraulic params if available, else fall back to delineation
    params_path = paths["product_outputs"] / "hydraulic_params.json"
    if params_path.exists():
        params = _load_json(params_path)
        channels = params.get("channels", [])
        stations = params.get("stations", {})
        boundaries = params.get("boundaries", {})
    else:
        channels = []
        stations = {}
        boundaries = {}

    if channels and stations:
        node_names = []
        for ch in channels:
            for n in [ch["node1"], ch["node2"]]:
                if n not in node_names:
                    node_names.append(n)

        n_j = len(node_names)
        n_l = len(channels)

        bc_flags = []
        for n in node_names:
            ntype = stations.get(n, {}).get("nodeType")
            is_bc = (n in boundaries) or (ntype in (1, 2))
            bc_flags.append(is_bc)

        sj_data = {
            "id": list(range(n_j)),
            "name": node_names,
            "z_inv": [float(stations.get(n, {}).get("zb", 500)) for n in node_names],
            "h_0": [2.0] * n_j,
            "bc": bc_flags,
            "A_sj": [float(stations.get(n, {}).get("Amin", 10000)) for n in node_names],
            "storage": ["functional"] * n_j,
            "a": [0.0] * n_j, "b": [0.0] * n_j, "c": [1.0] * n_j,
        }
        sl_data = {
            "id": list(range(n_l)),
            "name": [ch["name"] for ch in channels],
            "sj_0": [node_names.index(ch["node1"]) for ch in channels],
            "sj_1": [node_names.index(ch["node2"]) for ch in channels],
            "in_offset": [0.0] * n_l, "out_offset": [0.0] * n_l,
            "dx": [10000.0] * n_l,
            "n": [ch.get("manning_n", cfg["manning_n"]) for ch in channels],
            "shape": [cfg["default_shape"]] * n_l,
            "g1": [cfg["default_width"]] * n_l,
            "g2": [cfg["default_depth"]] * n_l,
            "g3": [0.0] * n_l, "g4": [0.0] * n_l,
            "Q_0": [_first_boundary_val(boundaries)] * n_l,
            "h_0": [2.0] * n_l,
            "A_s": [cfg["default_width"] * 2.0] * n_l,
            "ctrl": [False] * n_l,
            "A_c": [0.0] * n_l, "C": [0.0] * n_l,
            "C_uk": [0.0] * n_l, "C_dk": [0.0] * n_l,
        }
    else:
        raise FileNotFoundError("No hydraulic params or delineation available for network construction")

    superlinks = pd.DataFrame(sl_data)
    superjunctions = pd.DataFrame(sj_data)
    model = SuperLink(superlinks, superjunctions, internal_links=cfg.get("internal_links", 4))
    return model, boundaries, node_names


def run_hydraulics_steady(paths: dict[str, Path], cfg: dict) -> dict[str, Any]:
    """Steady-state convergence check. MUST pass before unsteady simulation."""
    model, boundaries, node_names = _build_superlink_network(paths, cfg)
    dt = cfg["dt_seconds"]
    max_iter = cfg["steady_state_max_iter"]
    tol = cfg["steady_state_tolerance"]

    params_path = paths["product_outputs"] / "hydraulic_params.json"
    hp_stations = {}
    if params_path.exists():
        hp_stations = _load_json(params_path).get("stations", {})

    Q_in = np.zeros(model.M)
    for j, name in enumerate(node_names):
        ntype = hp_stations.get(name, {}).get("nodeType")
        if name in boundaries and ntype == 2:
            Q_in[j] = float(boundaries[name])

    prev_H = model.H_j.copy()
    converged = False
    converge_iter = 0

    for i in range(max_iter):
        try:
            model.step(dt=dt, Q_in=Q_in)
        except Exception as e:
            return {"stage": "hydraulics_steady", "status": "error", "error": str(e), "iter": i}

        dH = np.max(np.abs(model.H_j - prev_H))
        prev_H = model.H_j.copy()
        if dH < tol:
            converged = True
            converge_iter = i + 1
            break

    steady_levels = {node_names[j]: float(model.H_j[j]) for j in range(model.M)}
    result = {
        "converged": converged,
        "iterations": converge_iter if converged else max_iter,
        "final_dH": float(dH),
        "tolerance": tol,
        "steady_state_levels_m": steady_levels,
        "upstream_inflow_m3s": float(Q_in[0]),
    }
    _write_json(paths["contracts"] / "hydraulics_steady.latest.json", result)
    status = "completed" if converged else "failed_convergence"
    return {"stage": "hydraulics_steady", "status": status, **result}


# ── Stage 6: Hydraulics Unsteady ─────────────────────────────────────────────

def _build_node_area_weights(paths: dict[str, Path], node_names: list[str]) -> np.ndarray:
    """按子流域面积比例构建节点入流权重向量。"""
    delin_path = paths["contracts"] / "delineation.latest.json"
    weights = np.zeros(len(node_names))
    if delin_path.exists():
        delin = _load_json(delin_path)
        basins = delin.get("basins", [])
        total_area = sum(b.get("area_km2", 0) for b in basins)
        if total_area > 0:
            for b in basins:
                bname = b.get("name", "")
                for j, nn in enumerate(node_names):
                    if bname in nn or nn in bname:
                        weights[j] = b["area_km2"] / total_area
                        break
    if np.sum(weights) < 1e-6:
        weights[0] = 1.0
    else:
        weights = weights / np.sum(weights)
    return weights


def run_hydraulics_unsteady(paths: dict[str, Path], cfg: dict) -> dict[str, Any]:
    """Unsteady 1D simulation. Requires steady-state to have passed first."""
    steady = _load_json(paths["contracts"] / "hydraulics_steady.latest.json")
    if not steady.get("converged"):
        return {"stage": "hydraulics_unsteady", "status": "blocked",
                "reason": "Steady state not converged. Fix steady-state first."}

    model, boundaries, node_names = _build_superlink_network(paths, cfg)
    dt = cfg["dt_seconds"]
    n_steps = int(cfg["simulation_hours"] * 3600 / dt)

    params_path = paths["product_outputs"] / "hydraulic_params.json"
    hp_stations = {}
    if params_path.exists():
        hp_stations = _load_json(params_path).get("stations", {})

    Q_ss_val = _first_boundary_val(boundaries)

    bc_inflow_indices = []
    Q_ss = np.zeros(model.M)
    for j, name in enumerate(node_names):
        ntype = hp_stations.get(name, {}).get("nodeType")
        if name in boundaries and ntype == 2:
            Q_ss[j] = float(boundaries[name])
            bc_inflow_indices.append(j)
    if not bc_inflow_indices:
        Q_ss[0] = Q_ss_val
        bc_inflow_indices = [0]

    for _ in range(200):
        model.step(dt=dt, Q_in=Q_ss)

    non_bc_indices = [j for j in range(model.M)
                      if j not in bc_inflow_indices
                      and not hp_stations.get(node_names[j], {}).get("nodeType") == 1]

    hp_full = _load_json(params_path) if params_path.exists() else {}
    basin_intervals = hp_full.get("basin_intervals", [])
    total_upstream_area = 0.0
    for name in node_names:
        rp = hp_full.get("reservoir_properties", {})
        for sid, info in rp.items():
            if info.get("name") and info["name"] in name and info.get("basin_area_km2"):
                total_upstream_area = max(total_upstream_area, info["basin_area_km2"])
                break
    total_inter_area = sum(b.get("area_km2", 0) for b in basin_intervals)
    lateral_fraction = total_inter_area / total_upstream_area if total_upstream_area > 0 else 0.05

    area_weights = _build_node_area_weights(paths, node_names)
    if non_bc_indices:
        bc_mask = np.zeros(model.M)
        bc_mask[non_bc_indices] = 1.0
        area_weights = area_weights * bc_mask
        w_sum = area_weights.sum()
        if w_sum > 0:
            area_weights = area_weights / w_sum
        area_weights = area_weights * lateral_fraction

    hydro_path = paths["contracts"] / "hydrology_sim.latest.json"
    if hydro_path.exists():
        hydro = _load_json(hydro_path)
        hydro_outflow = np.array(hydro.get("outflow_timeseries", []))
        hydro_dt = hydro["config"]["dt_hours"] * 3600
        hydro_mean = float(np.mean(np.abs(hydro_outflow[hydro_outflow > 0]))) if np.any(hydro_outflow > 0) else 1.0
        scale = Q_ss_val / hydro_mean if hydro_mean > 0 else 1.0
        hydro_outflow = hydro_outflow * scale
    else:
        hydro_outflow = np.array([Q_ss_val])
        hydro_dt = dt

    h_records = []
    for t in range(min(n_steps, 2000)):
        hydro_idx = min(int(t * dt / hydro_dt), len(hydro_outflow) - 1)
        raw_q = max(0.0, float(hydro_outflow[hydro_idx]))
        Q_in = Q_ss.copy()
        lateral = area_weights * raw_q
        for j in non_bc_indices:
            Q_in[j] += lateral[j]
        try:
            model.step(dt=dt, Q_in=Q_in)
            h_records.append(model.H_j.copy())
        except Exception:
            break

    if not h_records:
        return {"stage": "hydraulics_unsteady", "status": "error", "error": "No steps completed"}

    h_array = np.array(h_records)
    station_results = {}
    for j, name in enumerate(node_names):
        station_results[name] = {
            "max_level_m": float(np.max(h_array[:, j])),
            "min_level_m": float(np.min(h_array[:, j])),
            "final_level_m": float(h_array[-1, j]),
        }

    result = {
        "n_steps": len(h_records),
        "dt_seconds": dt,
        "stations": station_results,
    }
    _write_json(paths["contracts"] / "hydraulics_unsteady.latest.json", result)
    return {"stage": "hydraulics_unsteady", "status": "completed", "n_steps": len(h_records),
            "stations": {k: v["max_level_m"] for k, v in station_results.items()}}


# ── Stage 7: Coupled Hydrology-Hydraulics ────────────────────────────────────

def run_coupled(paths: dict[str, Path], cfg_hydro: dict, cfg_hydraulics: dict) -> dict[str, Any]:
    """Coupled simulation: hydrology feeds hydraulics at each time step."""
    delin = _load_json(paths["contracts"] / "delineation.latest.json")
    basins = sorted(delin["basins"], key=lambda b: -b["area_km2"])

    model, boundaries, node_names = _build_superlink_network(paths, cfg_hydraulics)
    dt_hydro_s = cfg_hydro["dt_hours"] * 3600
    dt_hyd = cfg_hydraulics["dt_seconds"]
    n_hydro_steps = int(cfg_hydro["simulation_hours"] / cfg_hydro["dt_hours"])
    substeps = max(1, int(dt_hydro_s / dt_hyd))

    # Load rainfall
    rain_series = np.zeros(n_hydro_steps)
    rain_series[min(24, n_hydro_steps):min(30, n_hydro_steps)] = 20.0

    # Warm up hydraulics to steady state
    Q_ss = np.zeros(model.M)
    Q_ss[0] = _first_boundary_val(boundaries)
    for _ in range(200):
        model.step(dt=dt_hyd, Q_in=Q_ss)

    area_weights = _build_node_area_weights(paths, node_names)

    runoff_modules = [_make_runoff(cfg_hydro["runoff_model"], cfg_hydro.get("runoff_params", {})) for _ in basins]
    routing_modules = [_make_routing(cfg_hydro["routing_model"], cfg_hydro.get("routing_params", {})) for _ in basins]

    coupled_h = []
    coupled_q = []

    for t in range(min(n_hydro_steps, 500)):
        basin_q = np.zeros(model.M)
        total_q = 0.0
        for i, basin in enumerate(basins):
            r = runoff_modules[i].run(float(rain_series[t]), 0.0)
            q = r * basin["area_km2"] * 1e6 / (dt_hydro_s * 1000)
            routed = routing_modules[i].run(q)
            total_q += routed
            bname = basin.get("name", "")
            for j, nn in enumerate(node_names):
                if bname in nn or nn in bname:
                    basin_q[j] += routed
                    break
            else:
                basin_q += area_weights * routed

        Q_in = basin_q if np.sum(basin_q) > 0 else area_weights * total_q
        for _ in range(substeps):
            try:
                model.step(dt=dt_hyd, Q_in=Q_in)
            except Exception:
                break

        coupled_h.append(model.H_j.copy())
        coupled_q.append(total_q)

    if not coupled_h:
        return {"stage": "coupled", "status": "error", "error": "No steps completed"}

    h_array = np.array(coupled_h)
    result = {
        "n_steps": len(coupled_h),
        "peak_inflow_m3s": float(np.max(coupled_q)),
        "stations": {
            node_names[j]: {
                "max_level_m": float(np.max(h_array[:, j])),
                "min_level_m": float(np.min(h_array[:, j])),
            }
            for j in range(model.M)
        },
    }
    _write_json(paths["contracts"] / "coupled_sim.latest.json", result)
    return {"stage": "coupled", "status": "completed", "n_steps": len(coupled_h),
            "peak_inflow_m3s": result["peak_inflow_m3s"]}


# ── Orchestrator ─────────────────────────────────────────────────────────────

ALL_STAGES = [
    "source_discovery", "data_pack", "delineation",
    "hydrology", "hydraulics_steady", "hydraulics_unsteady", "coupled",
]

def run_pipeline(case_id: str, config_path: str | None = None, stages: list[str] | None = None) -> dict[str, Any]:
    paths = resolve_paths(case_id)
    user_cfg = _load_yaml(Path(config_path)) if config_path else {}
    cfg = _merge_config(user_cfg, DEFAULT_CONFIG)
    active = stages or ALL_STAGES

    report = {"case_id": case_id, "pipeline": "full_modeling",
              "started_at": datetime.utcnow().isoformat(timespec="seconds"), "steps": []}

    # Context-based routing logic (SubTask 3.1, 3.2, 3.3, 4.1, 4.2)
    network_type = "natural_river"
    reservoir_nodes = []
    has_cross_sections = False

    knowledge_path = paths["contracts"] / "knowledge.latest.json"
    if knowledge_path.exists():
        k_data = _load_json(knowledge_path)
        assets = k_data.get("extracted_assets", [])
        if not assets and "assets" in k_data:
            assets = k_data["assets"]

        topo_asset = next((a for a in assets if a.get("data_type") == "RIVER_TOPO"), None)
        if topo_asset:
            payload = topo_asset.get("payload", {})
            network_type = payload.get("network_type", "natural_river")
            reservoir_nodes = [n for n in payload.get("nodes", []) if n.get("nodeType") == "reservoir"]

        has_cross_sections = any(
            str(asset.get("data_type") or "") == "CROSS_SECTION"
            or str(asset.get("data_type") or "").lower().startswith("cross_section")
            or str(asset.get("asset_type") or "").lower().startswith("cross_section")
            for asset in assets
        )

    try:
        source_bundle = _load_json(paths["source_bundle"])
        if _source_bundle_has_cross_sections(source_bundle):
            has_cross_sections = True
    except Exception:
        pass

    params_path = paths["product_outputs"] / "hydraulic_params.json"
    if params_path.exists():
        hp = _load_json(params_path)
        if _hydraulic_params_have_cross_sections(hp):
            has_cross_sections = True

    skip_d1 = False
    skip_d2 = False
    d1_skip_reason = ""
    d2_skip_reason = ""

    if network_type == "open_channel_transfer":
        if not reservoir_nodes:
            skip_d1 = True
            d1_skip_reason = OPEN_CHANNEL_TRANSFER_NO_RESERVOIR_REASON
        else:
            d1_skip_reason = "Running local hydrology for reservoir nodes only"

    if not has_cross_sections:
        skip_d2 = True
        d2_skip_reason = MISSING_CROSS_SECTION_REASON

    funcs = {
        "source_discovery": lambda: run_source_discovery(paths),
        "data_pack": lambda: run_data_pack(paths),
        "delineation": lambda: {
            "stage": "delineation",
            "status": "Skipped_NA",
            "reason": d1_skip_reason,
            "reason_code": OPEN_CHANNEL_TRANSFER_NO_RESERVOIR_REASON_CODE,
        } if skip_d1 else run_delineation(paths, cfg["delineation"]),
        "hydrology": lambda: {
            "stage": "hydrology",
            "status": "Skipped_NA",
            "reason": d1_skip_reason,
            "reason_code": OPEN_CHANNEL_TRANSFER_NO_RESERVOIR_REASON_CODE,
        } if skip_d1 else run_hydrology(paths, cfg["hydrology"]),
        "hydraulics_steady": lambda: {
            "stage": "hydraulics_steady",
            "status": "Skipped_Data_Missing",
            "reason": d2_skip_reason,
            "reason_code": MISSING_CROSS_SECTION_REASON_CODE,
        } if skip_d2 else run_hydraulics_steady(paths, cfg["hydraulics"]),
        "hydraulics_unsteady": lambda: {
            "stage": "hydraulics_unsteady",
            "status": "Skipped_Data_Missing",
            "reason": d2_skip_reason,
            "reason_code": MISSING_CROSS_SECTION_REASON_CODE,
        } if skip_d2 else run_hydraulics_unsteady(paths, cfg["hydraulics"]),
        "coupled": lambda: {
            "stage": "coupled",
            "status": "Skipped_NA",
            "reason": D1_OR_D2_SKIPPED_REASON,
            "reason_code": D1_OR_D2_SKIPPED_REASON_CODE,
        } if (skip_d1 or skip_d2) else run_coupled(paths, cfg["hydrology"], cfg["hydraulics"]),
    }

    downstream_block_reason = ""
    downstream_block_reason_code = ""
    blocked_downstream_stages = {"delineation", "hydrology", "hydraulics_steady", "hydraulics_unsteady", "coupled"}

    for i, stage in enumerate(active, 1):
        func = funcs.get(stage)
        if not func:
            print(f"[{i}/{len(active)}] Unknown: {stage}")
            continue
        if downstream_block_reason and stage in blocked_downstream_stages:
            step = {
                "stage": stage,
                "status": "Skipped_Data_Missing",
                "reason": downstream_block_reason,
                "reason_code": downstream_block_reason_code,
            }
            report["steps"].append(step)
            print(f"[{i}/{len(active)}] {stage}...")
            print(f"  -> {step.get('status', '?')}")
            continue
        print(f"[{i}/{len(active)}] {stage}...")
        try:
            step = func()
            report["steps"].append(step)
            print(f"  -> {step.get('status', '?')}")
            if (
                stage in {"source_discovery", "data_pack"}
                and str(step.get("status") or "").strip().lower() == "insufficient_data"
                and str(step.get("reason_code") or "") == NO_DELINEATION_READY_OUTLETS_REASON_CODE
            ):
                downstream_block_reason = NO_DELINEATION_READY_OUTLETS_REASON
                downstream_block_reason_code = NO_DELINEATION_READY_OUTLETS_REASON_CODE
        except Exception as e:
            report["steps"].append({"stage": stage, "status": "error", "error": str(e)})
            print(f"  -> ERROR: {e}")
            break

    statuses = [str(step.get("status") or "").strip().lower() for step in report["steps"]]
    failure_statuses = {"error", "failed", "quality_failed", "failed_convergence", "blocked"}
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
    elif any(status.startswith("skipped") or status in degraded_statuses for status in statuses):
        report_status = "degraded"
        quality_gate_passed = False
        degraded_steps = [step.get("stage") for step in report["steps"] if (str(step.get("status") or "").strip().lower().startswith("skipped") or str(step.get("status") or "").strip().lower() in degraded_statuses)]
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
    _write_json(paths["contracts"] / "full_pipeline_report.latest.json", report)
    print(f"\nReport: {paths['contracts'] / 'full_pipeline_report.latest.json'}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Modular deterministic modeling workflows")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--config", default=None, help="YAML config override")
    parser.add_argument(
        "--stages",
        default=None,
        help="Comma-separated stages, or 'all' for full chain: " + ",".join(ALL_STAGES),
    )
    args = parser.parse_args()
    stages: list[str] | None = None
    if args.stages:
        parts = [s.strip() for s in args.stages.split(",") if s.strip()]
        stages = None if parts == ["all"] else parts
    report = run_pipeline(case_id=args.case_id, config_path=args.config, stages=stages)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
