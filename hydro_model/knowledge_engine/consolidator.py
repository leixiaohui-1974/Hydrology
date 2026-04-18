"""Knowledge consolidator — writes evaluated results to YAML.

Follows the three-layer architecture (Pointer → Knowledge → Session).
Writes are incremental: existing knowledge is merged, not overwritten.
Each write carries _auto_generated metadata for traceability.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .evaluator import AUTO_ACCEPT_THRESHOLD, EvalResult
from .registry import MineResult
from .taxonomy import TYPE_CATALOG, DataType

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backup(path: Path, max_versions: int = 3) -> None:
    if not path.exists():
        return
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = path.with_suffix(f".v{ts}.yaml")
    shutil.copy2(path, backup)
    backups = sorted(path.parent.glob(f"{path.stem}.v*.yaml"))
    while len(backups) > max_versions:
        backups.pop(0).unlink()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120),
        encoding="utf-8",
    )


def _merge_dict(base: dict, update: dict) -> dict:
    """Deep-merge *update* into *base*; lists are replaced, not appended."""
    merged = dict(base)
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _merge_dict(merged[k], v)
        else:
            merged[k] = v
    return merged


# ── Per-type consolidation helpers ──────────────────────────────────────────

def _consolidate_geospatial(evals: list[EvalResult]) -> dict[str, Any]:
    items: list[dict] = []
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        items.append({
            "path": mr.source_path,
            "format": mr.payload.get("format", mr.source_kind),
            "crs": mr.payload.get("crs"),
            "bounds": mr.payload.get("bounds"),
            "resolution": mr.payload.get("resolution"),
            "quality_score": ev.quality.composite,
            "source": mr.source_kind,
            "_auto_generated": _now_iso(),
        })
    return {"sources": items, "count": len(items)}


def _consolidate_infrastructure(evals: list[EvalResult]) -> dict[str, Any]:
    entities: dict[str, dict] = {}
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        name = mr.payload.get("name", mr.payload.get("id", "unknown"))
        existing = entities.get(name, {})
        entry = {
            **existing,
            **{k: v for k, v in mr.payload.items() if v is not None},
            "source": mr.source_path,
            "quality_score": ev.quality.composite,
            "_auto_generated": _now_iso(),
        }
        entities[name] = entry
    return entities


def _consolidate_stations(evals: list[EvalResult]) -> dict[str, Any]:
    stations: dict[str, dict] = {}
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        name = mr.payload.get("name", "unknown")
        if name in stations and stations[name].get("quality_score", 0) >= ev.quality.composite:
            continue
        stations[name] = {
            "name": name,
            "lat": mr.payload.get("lat"),
            "lon": mr.payload.get("lon"),
            "type": mr.payload.get("station_type", mr.data_type.value),
            "control_area_km2": mr.payload.get("control_area_km2"),
            "source": mr.source_path,
            "quality_score": ev.quality.composite,
            "_auto_generated": _now_iso(),
        }
    return stations


def _consolidate_topology(evals: list[EvalResult]) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        best = _merge_dict(best, {
            **mr.payload,
            "source": mr.source_path,
            "quality_score": ev.quality.composite,
            "_auto_generated": _now_iso(),
        })
    return best


def _consolidate_hydraulic(evals: list[EvalResult]) -> dict[str, Any]:
    items: list[dict] = []
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        items.append({
            **mr.payload,
            "source": mr.source_path,
            "quality_score": ev.quality.composite,
            "_auto_generated": _now_iso(),
        })
    return {"entries": items, "count": len(items)}


def _consolidate_timeseries(evals: list[EvalResult]) -> dict[str, Any]:
    inventory: list[dict] = []
    for ev in evals:
        if ev.quality.composite < AUTO_ACCEPT_THRESHOLD:
            continue
        mr = ev.mine_result
        inventory.append({
            "variable": mr.payload.get("variable", "unknown"),
            "station": mr.payload.get("station"),
            "path": mr.source_path,
            "format": mr.source_kind,
            "n_records": mr.payload.get("n_records", 0),
            "time_step": mr.payload.get("time_step"),
            "start": mr.payload.get("start"),
            "end": mr.payload.get("end"),
            "quality_score": ev.quality.composite,
            "_auto_generated": _now_iso(),
        })
    return {"inventory": inventory, "total_series": len(inventory)}


_DOMAIN_CONSOLIDATORS = {
    "geospatial": _consolidate_geospatial,
    "infrastructure": _consolidate_infrastructure,
    "stations": _consolidate_stations,
    "topology": _consolidate_topology,
    "hydraulic": _consolidate_hydraulic,
    "timeseries": _consolidate_timeseries,
}


# ── Main consolidation ──────────────────────────────────────────────────────

def consolidate(
    evaluated: dict[str, list[EvalResult]],
    knowledge_dir: Path,
    *,
    backup: bool = True,
) -> dict[str, Any]:
    """Write evaluated results into the knowledge directory structure.

    Returns a summary of what was written.
    """
    from .taxonomy import DOMAIN_OF

    written: dict[str, str] = {}
    stats: dict[str, int] = {"accepted": 0, "skipped": 0}

    grouped_by_domain: dict[str, list[EvalResult]] = {}
    for dt_key, evals in evaluated.items():
        try:
            dt = DataType(dt_key)
        except ValueError:
            continue
        domain = DOMAIN_OF.get(dt)
        if domain is None:
            continue
        meta = TYPE_CATALOG.get(dt)
        if meta and meta.knowledge_path:
            target_path = knowledge_dir / meta.knowledge_path
            accepted = [e for e in evals if e.quality.verdict == "auto_accept"]
            if not accepted:
                stats["skipped"] += len(evals)
                continue
            stats["accepted"] += len(accepted)
            if backup:
                _backup(target_path)
            existing = _load_yaml(target_path)
            consolidator = _DOMAIN_CONSOLIDATORS.get(domain.value, _consolidate_hydraulic)
            new_data = consolidator(accepted)
            merged = _merge_dict(existing, {
                "_meta": {
                    "data_type": dt_key,
                    "last_consolidated": _now_iso(),
                    "source_count": len(accepted),
                },
                "data": new_data,
            })
            _write_yaml(target_path, merged)
            written[dt_key] = str(target_path.relative_to(knowledge_dir))
        else:
            grouped_by_domain.setdefault(domain.value, []).extend(evals)

    return {
        "knowledge_dir": str(knowledge_dir),
        "timestamp": _now_iso(),
        "files_written": written,
        "stats": stats,
    }


def update_manifest(knowledge_dir: Path, written: dict[str, str]) -> Path:
    """Update manifest.yaml with newly written files."""
    manifest_path = knowledge_dir / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    files = manifest.get("files", {})
    for dt_key, rel_path in written.items():
        meta = TYPE_CATALOG.get(DataType(dt_key))
        label = meta.label_cn if meta else dt_key
        files[rel_path] = label
    manifest["files"] = files
    manifest["_last_updated"] = _now_iso()
    _write_yaml(manifest_path, manifest)
    return manifest_path
