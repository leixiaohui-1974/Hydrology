"""通用知识挖掘引擎 — 不绑定任何特定 case。

通过 YAML 配置驱动，支持多种数据格式扫描、可靠性评分、异常检测、
参数提取。所有逻辑确定性，无随机性，无 AI 调用。

使用方式：
    import yaml
    from hydro_model.knowledge_mining import run_pipeline
    with open("configs/<case_id>.yaml") as f:
        config = yaml.safe_load(f)
    result = run_pipeline(config)
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _decimal_digits(value: float) -> int:
    """计算浮点数有效小数位数。"""
    s = f"{value:.15f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def _match_station(text: str, targets: list[str]) -> str | None:
    """确定性精确子串匹配。"""
    text_clean = text.strip()
    for target in targets:
        if target == text_clean or target in text_clean:
            return target
    return None


def _output_dir(config: dict) -> Path:
    return Path(config["output_dir"])


def _resolve_case_contract_path(config: dict, filename: str) -> Path | None:
    output_dir = _output_dir(config)
    candidates: list[Path] = []
    if len(output_dir.parents) >= 2:
        candidates.append(output_dir.parents[1] / "contracts" / filename)
    candidates.append(Path("cases") / str(config["case_id"]) / "contracts" / filename)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def _load_station_geolocation(config: dict) -> tuple[dict[str, Any], Path | None]:
    contract_path = _resolve_case_contract_path(config, "station_geolocation.latest.json")
    if contract_path is None:
        return {}, None
    try:
        payload = _load_json(contract_path)
    except Exception:
        return {}, contract_path
    return payload if isinstance(payload, dict) else {}, contract_path


def _load_station_proxy_outlet_anchors(config: dict) -> tuple[dict[str, Any], Path | None]:
    contract_path = _resolve_case_contract_path(config, "station_proxy_outlet_anchors.latest.json")
    if contract_path is None:
        return {}, None
    try:
        payload = _load_json(contract_path)
    except Exception:
        return {}, contract_path
    return payload if isinstance(payload, dict) else {}, contract_path


# ── 扫描器注册表 ────────────────────────────────────────────────────────────

def scan_json_topology(path: Path, targets: list[str]) -> list[dict]:
    """扫描智能体.json 格式的拓扑 JSON，提取节点坐标。"""
    candidates = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return candidates

    def _find_nodes(obj):
        if isinstance(obj, dict):
            if "nodes" in obj and isinstance(obj["nodes"], dict):
                return obj["nodes"]
            for v in obj.values():
                result = _find_nodes(v)
                if result is not None:
                    return result
        return None

    nodes = _find_nodes(data) or {}
    for node_name, node in nodes.items():
        x, y = node.get("x"), node.get("y")
        if x is None or y is None:
            continue
        # 去掉"前"/"后"/"入流"后缀做匹配
        clean = node_name.replace("前", "").replace("后", "").replace("入流", "").strip()
        matched = _match_station(clean, targets) or _match_station(node_name, targets)
        if matched is None:
            continue
        candidates.append({
            "name": matched, "lat": float(y), "lon": float(x),
            "source_path": str(path), "source_kind": "json_topology",
            "precision": min(_decimal_digits(float(y)), _decimal_digits(float(x))),
            "authority_level": "authoritative_candidate",
            "properties": {"node_name": node_name, "zb": node.get("zb"),
                          "nodeType": node.get("nodeType"), "Amin": node.get("Amin")},
        })
    return candidates


def scan_csv(path: Path, targets: list[str]) -> list[dict]:
    """扫描 CSV 文件，按列名匹配 lat/lon/name。"""
    candidates = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(text.splitlines())
        fields = reader.fieldnames or []
    except Exception:
        return candidates

    name_keys = [k for k in fields if any(w in k.lower() for w in ["name", "名", "站"])]
    lat_keys = [k for k in fields if any(w in k.lower() for w in ["lat", "纬"])]
    lon_keys = [k for k in fields if any(w in k.lower() for w in ["lon", "经"])]
    if not name_keys or not lat_keys or not lon_keys:
        return candidates

    for row_idx, row in enumerate(reader, start=2):
        name_val = row.get(name_keys[0], "").strip()
        matched = _match_station(name_val, targets)
        if matched is None:
            continue
        try:
            lat, lon = float(row[lat_keys[0]]), float(row[lon_keys[0]])
        except (ValueError, KeyError):
            continue
        candidates.append({
            "name": matched, "lat": lat, "lon": lon,
            "source_path": str(path), "source_kind": "csv",
            "precision": min(_decimal_digits(lat), _decimal_digits(lon)),
            "authority_level": "reference",
            "properties": {"row": row_idx, "raw_name": name_val},
        })
    return candidates


def scan_sqlite(path: Path, targets: list[str]) -> list[dict]:
    """扫描 SQLite 数据库中含 name/lat/lon 列的表。"""
    candidates = []
    try:
        conn = sqlite3.connect(str(path))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    except Exception:
        return candidates

    for table in tables:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
            cols_lower = [c.lower() for c in cols]
        except Exception:
            continue

        name_idx = next((i for i, c in enumerate(cols_lower)
                        if any(w in c for w in ["name", "名", "站"])), None)
        lat_idx = next((i for i, c in enumerate(cols_lower)
                       if "lat" in c or "纬" in c), None)
        lon_idx = next((i for i, c in enumerate(cols_lower)
                       if "lon" in c or "经" in c), None)
        if name_idx is None or lat_idx is None or lon_idx is None:
            continue

        try:
            rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
        except Exception:
            continue

        for row in rows:
            name_val = str(row[name_idx]).strip()
            # 去掉"一级"/"二级"等后缀
            clean = name_val.replace("一级", "").replace("二级", "").strip()
            matched = _match_station(clean, targets) or _match_station(name_val, targets)
            if matched is None:
                continue
            try:
                lat, lon = float(row[lat_idx]), float(row[lon_idx])
            except (ValueError, TypeError):
                continue
            extra = {}
            for i, col in enumerate(cols):
                if i not in (name_idx, lat_idx, lon_idx) and row[i] is not None:
                    extra[col] = row[i]
            candidates.append({
                "name": matched, "lat": lat, "lon": lon,
                "source_path": str(path), "source_kind": "sqlite",
                "precision": min(_decimal_digits(lat), _decimal_digits(lon)),
                "authority_level": "reference",
                "properties": {"table": table, "raw_name": name_val, **extra},
            })
    conn.close()
    return candidates


def scan_txt(path: Path, targets: list[str]) -> list[dict]:
    """扫描文本文件中的坐标对（name + lon,lat 交替行）。"""
    candidates = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return candidates

    for i, line in enumerate(lines):
        matched = _match_station(line.strip(), targets)
        if matched is None:
            continue
        # 下一行或同行找数字对
        numbers = re.findall(r"(\d+\.?\d*)", line)
        if len(numbers) < 2 and i + 1 < len(lines):
            numbers = re.findall(r"(\d+\.?\d*)", lines[i + 1])
        if len(numbers) >= 2:
            vals = [float(n) for n in numbers[:2]]
            lon, lat = (vals[0], vals[1]) if vals[0] > vals[1] else (vals[1], vals[0])
            if 70 < lon < 140 and 15 < lat < 55:
                candidates.append({
                    "name": matched, "lat": lat, "lon": lon,
                    "source_path": str(path), "source_kind": "text",
                    "precision": min(_decimal_digits(lat), _decimal_digits(lon)),
                    "authority_level": "supporting_evidence",
                    "properties": {"line": i + 1, "raw_text": line.strip()},
                })
    return candidates


SCANNERS = {
    ".json": scan_json_topology,
    ".csv": scan_csv,
    ".sqlite3": scan_sqlite,
    ".db": scan_sqlite,
    ".txt": scan_txt,
}


# ── Stage 1: Discover ───────────────────────────────────────────────────────

def discover(config: dict) -> dict:
    """扫描所有配置目录，发现站点坐标候选。"""
    targets = config["target_stations"]
    exts = set(config.get("scan_extensions", SCANNERS.keys()))
    all_candidates = []
    scanned_files = []

    for scan_dir in config.get("scan_dirs", []):
        scan_dir = Path(scan_dir)
        if not scan_dir.exists():
            continue
        for ext in exts:
            scanner = SCANNERS.get(ext)
            if scanner is None:
                continue
            for fpath in sorted(scan_dir.rglob(f"*{ext}")):
                found = scanner(fpath, targets)
                if found:
                    scanned_files.append(str(fpath))
                    all_candidates.extend(found)

    # 去重：同源同坐标
    seen = set()
    unique = []
    for c in all_candidates:
        key = (c["source_path"], c["name"], round(c["lat"], 9), round(c["lon"], 9))
        if key not in seen:
            seen.add(key)
            unique.append(c)

    payload = {
        "case_id": config["case_id"],
        "stage": "discover",
        "scanned_files": len(set(scanned_files)),
        "candidates": len(unique),
        "by_station": {t: len([c for c in unique if c["name"] == t]) for t in targets},
        "data": unique,
    }
    _write_json(_output_dir(config) / "source_inventory.json", payload)
    return payload


# ── Stage 2: Inspect ─────────────────────────────────────────────────────────

def inspect(config: dict) -> dict:
    """DEM 范围检验所有候选坐标。"""
    inventory = _load_json(_output_dir(config) / "source_inventory.json")
    dem_path = config.get("dem_path")
    dem_bounds = None

    if dem_path and Path(dem_path).exists():
        try:
            import rasterio
            with rasterio.open(dem_path) as ds:
                b = ds.bounds
                dem_bounds = {"left": b.left, "bottom": b.bottom,
                             "right": b.right, "top": b.top}
        except Exception:
            pass

    for c in inventory["data"]:
        if dem_bounds:
            c["inside_dem"] = (
                dem_bounds["left"] <= c["lon"] <= dem_bounds["right"]
                and dem_bounds["bottom"] <= c["lat"] <= dem_bounds["top"]
            )
        else:
            c["inside_dem"] = None

    payload = {
        "case_id": config["case_id"],
        "stage": "inspect",
        "dem_path": dem_path,
        "dem_bounds": dem_bounds,
        "candidates": inventory["data"],
    }
    _write_json(_output_dir(config) / "inspection.json", payload)
    return payload


# ── Stage 3: Score ───────────────────────────────────────────────────────────

WEIGHT_PRECISION = 0.25
WEIGHT_DEM = 0.20
WEIGHT_RIVER = 0.30
WEIGHT_CONSISTENCY = 0.25

PRECISION_SCORES = {0: 0.0, 1: 0.2, 2: 0.5, 3: 0.7, 4: 0.85, 5: 0.95}


def _score_precision(digits: int) -> float:
    return PRECISION_SCORES.get(digits, 1.0 if digits >= 6 else 0.0)


def _load_river_coords(config: dict) -> np.ndarray | None:
    rpath = config.get("river_network_path")
    if not rpath or not Path(rpath).exists():
        return None
    try:
        import geopandas as gpd
        gdf = gpd.read_file(rpath)
        if gdf.crs and not gdf.crs.is_geographic:
            gdf = gdf.to_crs("EPSG:4326")
        coords = []
        for geom in gdf.geometry:
            if geom is None:
                continue
            if hasattr(geom, "coords"):
                coords.extend(geom.coords)
            elif hasattr(geom, "geoms"):
                for part in geom.geoms:
                    if hasattr(part, "coords"):
                        coords.extend(part.coords)
        arr = np.array([(c[0], c[1]) for c in coords]) if coords else None
        if arr is not None and len(arr) > 10000:
            arr = arr[::max(1, len(arr) // 10000)]  # 确定性子采样
        return arr
    except Exception:
        return None


def _river_distance_km(lat: float, lon: float, river_coords: np.ndarray | None) -> float | None:
    if river_coords is None:
        return None
    dlat = (river_coords[:, 1] - lat) * 111.32
    dlon = (river_coords[:, 0] - lon) * 111.32 * np.cos(np.radians(lat))
    return float(np.min(np.sqrt(dlat**2 + dlon**2)))


def score(config: dict) -> dict:
    """多维可靠性评分：精度、DEM、河网距离、多源一致性。"""
    inspection = _load_json(_output_dir(config) / "inspection.json")
    candidates = inspection["candidates"]
    river_coords = _load_river_coords(config)

    # 按站点分组
    by_station: dict[str, list[dict]] = {}
    for c in candidates:
        by_station.setdefault(c["name"], []).append(c)

    for c in candidates:
        # 精度评分
        s_prec = _score_precision(c["precision"])

        # DEM 范围评分
        s_dem = 1.0 if c.get("inside_dem") else (0.5 if c.get("inside_dem") is None else 0.0)

        # 河网距离评分
        dist = _river_distance_km(c["lat"], c["lon"], river_coords)
        c["river_distance_km"] = dist
        if dist is None:
            s_river = 0.5
        elif dist < 1.0:
            s_river = 1.0
        elif dist < 5.0:
            s_river = 0.7
        elif dist < 15.0:
            s_river = 0.3
        else:
            s_river = 0.0

        # 多源一致性评分
        peers = by_station.get(c["name"], [])
        if len(peers) <= 1:
            s_consist = 0.3
        else:
            agree = sum(
                1 for p in peers
                if p["source_path"] != c["source_path"]
                and np.sqrt(((p["lat"] - c["lat"]) * 111.32)**2 +
                           ((p["lon"] - c["lon"]) * 111.32 * np.cos(np.radians(c["lat"])))**2) < 5.0
            )
            total_other = len(peers) - 1
            s_consist = 1.0 if agree / total_other >= 0.5 else (0.5 if agree > 0 else 0.1)

        c["score"] = round(
            WEIGHT_PRECISION * s_prec + WEIGHT_DEM * s_dem +
            WEIGHT_RIVER * s_river + WEIGHT_CONSISTENCY * s_consist, 4
        )
        c["score_detail"] = {
            "precision": round(s_prec, 3), "dem": round(s_dem, 3),
            "river": round(s_river, 3), "consistency": round(s_consist, 3),
        }

    # 选出每站最佳（确定性排序：score desc, precision desc, source_path asc）
    best = {}
    for name, group in by_station.items():
        group.sort(key=lambda c: (-c["score"], -c["precision"], c["source_path"]))
        best[name] = group[0]
        for c in group:
            c["is_best"] = (c is group[0])

    payload = {
        "case_id": config["case_id"],
        "stage": "score",
        "candidates": candidates,
        "best_per_station": {k: {"name": v["name"], "lat": v["lat"], "lon": v["lon"],
                                  "score": v["score"], "source_kind": v["source_kind"]}
                             for k, v in best.items()},
    }
    _write_json(_output_dir(config) / "source_reliability.json", payload)
    return payload


# ── Stage 4: Validate ────────────────────────────────────────────────────────

def validate(config: dict) -> dict:
    """异常检测：经纬度范围、离群点、低精度。"""
    scoring = _load_json(_output_dir(config) / "source_reliability.json")
    candidates = scoring["candidates"]
    val_cfg = config.get("validation", {})
    lat_range = val_cfg.get("lat_range", [15.0, 55.0])
    lon_range = val_cfg.get("lon_range", [70.0, 140.0])
    outlier_thresh = val_cfg.get("outlier_threshold_deg", 1.5)
    min_prec = val_cfg.get("min_precision_digits", 2)

    # 计算中位纬度（用 inside_dem 的候选）
    inside_lats = [c["lat"] for c in candidates if c.get("inside_dem")]
    median_lat = sorted(inside_lats)[len(inside_lats) // 2] if inside_lats else (lat_range[0] + lat_range[1]) / 2

    anomalies = []
    for c in candidates:
        issues = []
        if not (lat_range[0] <= c["lat"] <= lat_range[1]):
            issues.append({"rule": "lat_range", "severity": "fail",
                          "message": f"纬度 {c['lat']} 超出范围 {lat_range}"})
        if not (lon_range[0] <= c["lon"] <= lon_range[1]):
            issues.append({"rule": "lon_range", "severity": "fail",
                          "message": f"经度 {c['lon']} 超出范围 {lon_range}"})
        if abs(c["lat"] - median_lat) > outlier_thresh:
            issues.append({"rule": "lat_outlier", "severity": "fail",
                          "message": f"纬度 {c['lat']} 偏离中位数 {median_lat:.2f} 超过 {outlier_thresh}°"})
        if c["precision"] < min_prec:
            issues.append({"rule": "low_precision", "severity": "warn",
                          "message": f"精度仅 {c['precision']} 位小数"})
        if issues:
            anomalies.append({"name": c["name"], "lat": c["lat"], "lon": c["lon"],
                             "source_path": c["source_path"], "issues": issues})

    payload = {
        "case_id": config["case_id"],
        "stage": "validate",
        "median_lat": median_lat,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
    _write_json(_output_dir(config) / "coordinate_validation.json", payload)
    return payload


# ── Stage 5: Normalize ───────────────────────────────────────────────────────

def normalize(config: dict) -> dict:
    """输出 delineation-ready outlets 和 control_station_mapping。"""
    scoring = _load_json(_output_dir(config) / "source_reliability.json")
    validation = _load_json(_output_dir(config) / "coordinate_validation.json")
    station_geolocation, station_geolocation_path = _load_station_geolocation(config)
    station_proxy_anchors, station_proxy_anchors_path = _load_station_proxy_outlet_anchors(config)

    best = scoring["best_per_station"]
    candidates = scoring["candidates"]
    geolocation_by_station = {
        str(row.get("canonical_name") or row.get("station_id") or "").strip(): row
        for row in (station_geolocation.get("stations") or [])
        if isinstance(row, dict) and str(row.get("canonical_name") or row.get("station_id") or "").strip()
    }
    proxy_anchor_by_station = {
        str(row.get("station_name") or row.get("station_id") or "").strip(): row
        for row in (station_proxy_anchors.get("station_proxy_anchors") or [])
        if isinstance(row, dict) and str(row.get("station_name") or row.get("station_id") or "").strip()
    }
    unassigned_proxy_anchors = [
        row for row in (station_proxy_anchors.get("unassigned_case_proxy_anchors") or []) if isinstance(row, dict)
    ]

    # 异常坐标集合（只看 best 候选是否异常）
    anomaly_coords = {
        (a["name"], round(a["lat"], 6), round(a["lon"], 6))
        for a in validation.get("anomalies", [])
        if any(i["severity"] == "fail" for i in a.get("issues", []))
    }

    # 构建映射和 outlets
    mappings = []
    outlets = []
    review_candidates = []
    for idx, station_name in enumerate(config["target_stations"], start=1):
        choice = best.get(station_name)
        if not choice:
            geolocation_row = geolocation_by_station.get(station_name) or {}
            proxy_anchor = proxy_anchor_by_station.get(station_name) or {}
            fallback_status = str(geolocation_row.get("geolocation_status") or "").strip() or "missing"
            if proxy_anchor:
                fallback_status = "proxy_anchor_linked"
            mapping = {
                "id": f"{config['case_id']}-station-{idx:02d}",
                "name": station_name,
                "status": fallback_status,
            }
            if geolocation_row:
                mapping.update(
                    {
                        "geolocation_status": fallback_status,
                        "query_candidates": list(geolocation_row.get("query_candidates") or []),
                        "context_evidence_refs": list(geolocation_row.get("context_evidence_refs") or []),
                        "blocked_public_data_kinds": list(geolocation_row.get("blocked_public_data_kinds") or []),
                        "evidence_count": len(list(geolocation_row.get("context_evidence_refs") or [])),
                    }
                )
                review_candidates.append(
                    {
                        "name": station_name,
                        "geolocation_status": fallback_status,
                        "query_candidates": list(geolocation_row.get("query_candidates") or []),
                        "context_evidence_refs": list(geolocation_row.get("context_evidence_refs") or []),
                        "blocked_public_data_kinds": list(geolocation_row.get("blocked_public_data_kinds") or []),
                    }
                )
            if proxy_anchor:
                mapping.update(
                    {
                        "proxy_anchor_status": proxy_anchor.get("proxy_anchor_status"),
                        "proxy_anchor_ref": proxy_anchor.get("anchor_id"),
                        "proxy_anchor_kind": proxy_anchor.get("anchor_kind"),
                        "proxy_anchor_confidence": proxy_anchor.get("confidence"),
                        "proxy_anchor_lat": proxy_anchor.get("lat"),
                        "proxy_anchor_lon": proxy_anchor.get("lon"),
                        "proxy_anchor_display_name": proxy_anchor.get("display_name"),
                    }
                )
                review_candidates.append(
                    {
                        "name": station_name,
                        "proxy_anchor_status": proxy_anchor.get("proxy_anchor_status"),
                        "proxy_anchor_ref": proxy_anchor.get("anchor_id"),
                        "proxy_anchor_kind": proxy_anchor.get("anchor_kind"),
                        "proxy_anchor_confidence": proxy_anchor.get("confidence"),
                        "proxy_anchor_display_name": proxy_anchor.get("display_name"),
                    }
                )
            mappings.append(mapping)
            continue

        # 收集该站点的所有证据
        evidence = sorted(
            [c for c in candidates if c["name"] == station_name],
            key=lambda c: (-c["score"], -c["precision"], c["source_path"]),
        )

        is_anomalous = (station_name, round(choice["lat"], 6), round(choice["lon"], 6)) in anomaly_coords
        status = "proposed_authoritative" if choice["score"] >= 0.7 and not is_anomalous else "review_required"

        mappings.append({
            "id": f"{config['case_id']}-station-{idx:02d}",
            "name": station_name,
            "status": status,
            "lat": choice["lat"], "lon": choice["lon"],
            "score": choice["score"],
            "source_kind": choice["source_kind"],
            "evidence_count": len(evidence),
        })

        if status == "proposed_authoritative":
            outlets.append({
                "outlet_id": f"{config['case_id']}-outlet-{idx:02d}",
                "name": station_name,
                "lat": choice["lat"], "lon": choice["lon"],
                "geometry_confidence": status,
                "source": choice.get("source_kind"),
            })

    mapping_payload = {
        "case_id": config["case_id"], "stage": "normalize",
        "mappings": mappings,
        "normalization_inputs": {
            "station_geolocation_contract": str(station_geolocation_path) if station_geolocation_path else None,
            "station_geolocation_status": station_geolocation.get("geolocation_status"),
            "station_proxy_outlet_anchors_contract": str(station_proxy_anchors_path) if station_proxy_anchors_path else None,
            "station_proxy_outlet_anchor_status": station_proxy_anchors.get("anchor_status"),
        },
    }
    ready_payload = {
        "case_id": config["case_id"],
        "workflow": "watershed_delineation",
        "filter_rules": ["score >= 0.7", "no fail-severity anomalies"],
        "excluded": [m["name"] for m in mappings if m.get("status") != "proposed_authoritative"],
        "count": len(outlets),
        "outlets": outlets,
        "review_candidates": review_candidates,
        "proxy_anchor_candidates": unassigned_proxy_anchors,
        "normalization_inputs": {
            "station_geolocation_contract": str(station_geolocation_path) if station_geolocation_path else None,
            "station_geolocation_status": station_geolocation.get("geolocation_status"),
            "station_proxy_outlet_anchors_contract": str(station_proxy_anchors_path) if station_proxy_anchors_path else None,
            "station_proxy_outlet_anchor_status": station_proxy_anchors.get("anchor_status"),
        },
        "notes": (
            "No delineation-ready outlets yet; station geolocation and proxy anchor evidence are available for review-driven coordinate resolution."
            if review_candidates or unassigned_proxy_anchors
            else "No delineation-ready outlets were found."
        ),
    }
    _write_json(_output_dir(config) / "control_station_mapping.json", mapping_payload)
    _write_json(_output_dir(config) / "outlets.delineation_ready.json", ready_payload)
    return {"mapping": mapping_payload, "delineation_ready": ready_payload}


# ── Stage 6: Hydraulic Parameters ────────────────────────────────────────────

def discover_hydraulic_params(config: dict) -> dict:
    """从 topology JSON 和 SQLite 提取水力模型参数。"""
    params: dict[str, Any] = {
        "case_id": config["case_id"], "stage": "hydraulic_params",
        "sources": {}, "stations": {}, "channels": [], "sections_count": 0,
        "turbines": {}, "gates": {}, "boundaries": {},
        "initial_conditions": {}, "basin_intervals": [],
        "reservoir_properties": {}, "timeseries_inventory": [],
    }

    # 从 topology JSON 提取
    for topo_path in config.get("topology_json_paths", []):
        topo_path = Path(topo_path)
        if not topo_path.exists():
            continue
        params["sources"]["json_" + topo_path.name] = str(topo_path)
        data = _load_json(topo_path)

        def _find_at(obj, key):
            if isinstance(obj, dict):
                if key in obj:
                    return obj[key]
                for v in obj.values():
                    r = _find_at(v, key)
                    if r is not None:
                        return r
            return None

        base = _find_at(data, "baseData") or {}
        ini = _find_at(data, "initialData") or {}

        for name, node in (base.get("nodes") or {}).items():
            if node.get("x") is not None and node.get("y") is not None:
                params["stations"][name] = {
                    "source": "json_topology", "zb": node.get("zb"),
                    "Amin": node.get("Amin"), "nodeType": node.get("nodeType"),
                    "lon": node.get("x"), "lat": node.get("y"),
                }

        for name, ch in (base.get("channels") or {}).items():
            sec_names = ch.get("sec_names", [])
            params["channels"].append({
                "name": name, "node1": ch.get("node1"), "node2": ch.get("node2"),
                "manning_n": ch.get("nc"),
                "section_count": len(sec_names) if isinstance(sec_names, list) else 0,
            })

        params["sections_count"] = len(base.get("sections") or {})

        for k, v in (ini.get("turbines") or {}).items():
            station = k.replace("水轮机", "").rstrip("0123456789")
            params["turbines"].setdefault(station, []).append({"name": k, "initial_value": v})

        for k, v in (ini.get("gates") or {}).items():
            station = k.replace("闸", "").rstrip("0123456789")
            params["gates"].setdefault(station, []).append({"name": k, "initial_opening": v})

        params["boundaries"].update(ini.get("boundaries") or {})
        params["initial_conditions"].update((ini.get("channels") or {}).get("local_Z") or {})

    # 从 SQLite 提取
    for db_path in config.get("sqlite_paths", []):
        db_path = Path(db_path)
        if not db_path.exists():
            continue
        params["sources"]["sqlite_" + db_path.name] = str(db_path)
        conn = sqlite3.connect(str(db_path))

        try:
            for r in conn.execute(
                "SELECT id, name, elevation, basin_area_km2, metadata_json FROM stations"
            ).fetchall():
                meta = json.loads(r[4]) if r[4] else {}
                params["reservoir_properties"][r[0]] = {
                    "name": r[1], "elevation": r[2], "basin_area_km2": r[3],
                    "normal_pool": meta.get("normal_pool"),
                    "dead_pool": meta.get("dead_pool"),
                    "installed_capacity_mw": meta.get("installed_capacity_mw"),
                }
        except Exception:
            pass

        try:
            for b in conn.execute("SELECT * FROM basins").fetchall():
                params["basin_intervals"].append({
                    "id": b[0], "name": b[1], "area_km2": b[2],
                    "upstream": b[3], "downstream": b[4],
                })
        except Exception:
            pass

        try:
            for t in conn.execute(
                "SELECT station_id, variable, time_step, n_records FROM timeseries_meta"
            ).fetchall():
                params["timeseries_inventory"].append({
                    "station_id": t[0], "variable": t[1],
                    "time_step": t[2], "n_records": t[3],
                })
        except Exception:
            pass

        conn.close()

    _write_json(_output_dir(config) / "hydraulic_params.json", params)
    return params


# ── Orchestrator ─────────────────────────────────────────────────────────────

STAGES = {
    "discover": discover,
    "inspect": inspect,
    "score": score,
    "validate": validate,
    "normalize": normalize,
    "hydraulic_params": discover_hydraulic_params,
}


def run_pipeline(config: dict, stages: list[str] | None = None) -> dict:
    """运行知识挖掘全流程。确定性：同配置 = 同结果。"""
    active = stages or list(STAGES.keys())
    results = {"case_id": config["case_id"], "stages": {}}
    for stage_name in active:
        func = STAGES.get(stage_name)
        if func is None:
            continue
        results["stages"][stage_name] = func(config)
    return results
