from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

_results_override = os.environ.get("HYDROLOGY_RESULTS_DIR")
RESULTS_DIR = Path(_results_override) if _results_override else BASE_DIR / "examples" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_workspace_relpath(raw: str | Path) -> Path:
    """Resolve a path; if relative, interpret from WORKSPACE (monorepo root)."""
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (WORKSPACE / p).resolve()


def abs_path(raw: str | None, *, label: str, required: bool = True) -> Path | None:
    if not raw:
        if required:
            raise ValueError(f"{label} is required")
        return None
    resolved = resolve_workspace_relpath(raw)
    if required and not resolved.exists():
        raise FileNotFoundError(f"{label} does not exist: {resolved}")
    return resolved


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_python(module_path: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(module_path), *args]
    subprocess.run(cmd, check=True)


def _read_case_config(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """Read case YAML once and resolve workspace-relative paths."""
    if config_path:
        cfg_file = Path(config_path)
    else:
        cfg_file = BASE_DIR / "configs" / f"{case_id}.yaml"
    if not cfg_file.exists():
        return {"case_id": case_id}
    with open(cfg_file, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("case_id", case_id)
    return resolve_config_paths(cfg, WORKSPACE)


def load_case_config(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """加载 case 配置并将相对路径解析为绝对路径。

    自动合并知识层：如果 knowledge/{case_id}/ 目录存在，
    将分层知识文件加载到 cfg["knowledge"] 中，确保所有
    工作流无需修改即可访问拆分后的知识数据。
    """
    cfg = _read_case_config(case_id, config_path)

    if "knowledge" not in cfg or not cfg["knowledge"]:
        kb = load_knowledge(case_id, config_path)
        if kb:
            cfg["knowledge"] = kb

    return cfg


def resolve_config_paths(cfg: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """将配置中的相对路径基于 workspace 解析为绝对路径。"""
    path_keys = [
        "dem_path", "river_network_path", "source_bundle_path",
        "case_manifest_path", "output_dir",
        "yjdt_params_source", "yjdt_params_scheme", "yjdt_integration_report",
    ]
    list_path_keys = ["scan_dirs", "topology_json_paths", "sqlite_paths"]

    for key in path_keys:
        val = cfg.get(key)
        if val and not Path(val).is_absolute():
            cfg[key] = str((workspace / val).resolve())

    for key in list_path_keys:
        items = cfg.get(key, [])
        resolved = []
        for item in items:
            if item and not Path(item).is_absolute():
                resolved.append(str((workspace / item).resolve()))
            else:
                resolved.append(item)
        if resolved:
            cfg[key] = resolved

    return cfg


# ── 知识目录加载（v3.0 分层架构） ────────────────────────────────────────────

def load_knowledge(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """加载知识目录。

    优先从 knowledge/{case_id}/ 目录读取分层文件；
    如果目录不存在，回退到 config YAML 内嵌的 knowledge 段（兼容旧格式）。
    """
    kb_dir = BASE_DIR / "knowledge" / case_id
    manifest_path = kb_dir / "manifest.yaml"

    if manifest_path.exists():
        return _load_knowledge_dir(kb_dir)

    cfg = _read_case_config(case_id, config_path)
    return cfg.get("knowledge", {})


def _load_knowledge_dir(kb_dir: Path) -> dict[str, Any]:
    """从知识目录加载所有 YAML 文件，返回统一字典。"""
    knowledge: dict[str, Any] = {}

    manifest = yaml.safe_load((kb_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
    knowledge["_manifest"] = manifest

    file_map = {
        "params/hydraulics.yaml": "params_hydraulics",
        "params/hydrology.yaml": "params_hydrology",
        "params/control.yaml": "params_control",
        "params/horton.yaml": "horton_params",
        "topology/topology.yaml": "topology",
        "topology/reservoirs.yaml": "reservoirs",
        "topology/turbines.yaml": "turbines",
        "topology/gates.yaml": "gates",
        "topology/sections.yaml": "sections",
        "terrain/index.yaml": "terrain_sections",
        "curves/zv_curves.yaml": "zv_curves",
        "precision/history.yaml": "precision_history",
        "assets/inventory.yaml": "discovered_assets",
        "assets/scada.yaml": "scada_timeseries",
        "assets/boundary.yaml": "boundary_conditions_csv",
    }

    for rel_path, key in file_map.items():
        full_path = kb_dir / rel_path
        if full_path.exists():
            try:
                knowledge[key] = yaml.safe_load(full_path.read_text(encoding="utf-8")) or {}
            except Exception:
                knowledge[key] = {}

    model_cards = {}
    models_dir = kb_dir / "models"
    if models_dir.exists():
        for f in models_dir.glob("*.yaml"):
            try:
                model_cards[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
    knowledge["model_cards"] = model_cards

    return knowledge


def save_knowledge_file(case_id: str, rel_path: str, data: Any) -> Path:
    """写入知识目录中的单个文件。"""
    kb_dir = BASE_DIR / "knowledge" / case_id
    target = kb_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return target


def run_knowledge_mining(case_id: str, config_path: str | None = None) -> dict[str, Any]:
    """运行知识挖掘引擎全流程（供任意 workflow 按需调用）。

    Usage:
        from workflows._shared import run_knowledge_mining
        result = run_knowledge_mining("daduhe")
    """
    from hydro_model.knowledge_engine import run_full_pipeline
    return run_full_pipeline(case_id, config_path=config_path)


# ── 配置派生的映射构建器（零硬编码） ─────────────────────────────────────
#
# 所有 workflow 统一调用这些函数，禁止在各自文件内维护案例专属 dict。
# 数据全部来自 cfg["knowledge"]["reservoirs"] + cfg["knowledge"]["topology"]。


import re as _re

_SUFFIX_RE = _re.compile(r"[一二三四五六七八九十\d]+级$|电站$|水库$|水电站$")


def get_station_ids(cfg: dict[str, Any]) -> list[str]:
    """返回所有 station_id 的有序列表（如 ["s1","s2",...]）。

    优先从 knowledge.reservoirs 取（按 key 排序），回退到 target_stations。
    """
    reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})
    if isinstance(reservoirs, dict) and reservoirs:
        return sorted(reservoirs.keys())
    ts = cfg.get("target_stations", [])
    if ts:
        return list(ts)
    return []


def build_name_to_sid(cfg: dict[str, Any]) -> dict[str, str]:
    """从 knowledge.reservoirs 构建 名称→station_id 映射。

    自动生成短名别名（"枕头坝一级" → "枕头坝"）以兼容节点/文件名。
    """
    reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})
    mapping: dict[str, str] = {}
    if not isinstance(reservoirs, dict):
        return mapping
    for sid, info in reservoirs.items():
        if not isinstance(info, dict):
            continue
        mapping[sid] = sid
        name = info.get("name", "")
        if name:
            mapping[name] = sid
            short = _SUFFIX_RE.sub("", name).strip()
            if short and short != name:
                mapping.setdefault(short, sid)
    return mapping


def build_sid_to_name(cfg: dict[str, Any]) -> dict[str, str]:
    """station_id → 中文显示名（如 s1 → 瀑布沟）。"""
    reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})
    mapping: dict[str, str] = {}
    if not isinstance(reservoirs, dict):
        return mapping
    for sid, info in reservoirs.items():
        if isinstance(info, dict):
            mapping[sid] = info.get("name", sid)
    return mapping


def build_station_meta(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """构建 station_id → {name, normal_pool_m, dead_pool_m, vars, ...} 元数据。

    vars 字段自动根据 project_type 推断标准变量集：
    - cascade_hydro: [H_up, Q_in, Q_out]
    - water_transfer: [H_up, Q_in, Q_out, Q_transfer]
    """
    reservoirs = cfg.get("knowledge", {}).get("reservoirs", {})
    project_type = cfg.get("project_type", "cascade_hydro")
    base_vars = ["H_up", "Q_in", "Q_out"]
    if "transfer" in project_type:
        base_vars.append("Q_transfer")

    meta: dict[str, dict[str, Any]] = {}
    if not isinstance(reservoirs, dict):
        return meta
    for sid, info in reservoirs.items():
        if not isinstance(info, dict):
            continue
        meta[sid] = {
            "name": info.get("name", sid),
            "normal_pool_m": info.get("normal_pool_m"),
            "dead_pool_m": info.get("dead_pool_m"),
            "installed_capacity_mw": info.get("installed_capacity_mw"),
            "basin_area_km2": info.get("basin_area_km2"),
            "vars": list(base_vars),
        }
    return meta


def build_channel_to_station(cfg: dict[str, Any]) -> dict[str, str]:
    """channel_name → station_id（基于 topology.channels.node2 匹配 reservoirs）。"""
    channels = cfg.get("knowledge", {}).get("topology", {}).get("channels", [])
    name_to_sid = build_name_to_sid(cfg)
    mapping: dict[str, str] = {}
    if not isinstance(channels, list):
        return mapping
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        ch_name = ch.get("name", "")
        if not ch_name:
            continue
        for node_key in ("node2", "node1"):
            raw = ch.get(node_key, "")
            bare = raw.replace("前", "").replace("后", "").replace("入流", "").replace("出流", "")
            sid = name_to_sid.get(bare, "")
            if sid:
                mapping[ch_name] = sid
                break
    return mapping


def build_channel_map(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """完整 channel_map：channel_name → {station, manning_n, prefix, ...}。"""
    channels = cfg.get("knowledge", {}).get("topology", {}).get("channels", [])
    ch_to_station = build_channel_to_station(cfg)
    default_n = cfg.get("modeling", {}).get("hydraulics", {}).get("manning_n", 0.025)
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(channels, list):
        return result
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        ch_name = ch.get("name", "")
        if not ch_name:
            continue
        prefix_parts = ch_name.upper().split("-")
        result[ch_name] = {
            "station": ch_to_station.get(ch_name, ""),
            "prefix": [p[:2] for p in prefix_parts if p],
            "manning_n": ch.get("manning_n", default_n),
            "node1": ch.get("node1", ""),
            "node2": ch.get("node2", ""),
        }
    return result


def build_channel_keywords(cfg: dict[str, Any]) -> list[tuple[str, str]]:
    """从 topology 节点名构建 (关键词, channel_name) 列表，按长度降序。

    用于在文件路径中搜索关键词以推断所属 channel。
    """
    channels = cfg.get("knowledge", {}).get("topology", {}).get("channels", [])
    pairs: list[tuple[str, str]] = []
    if not isinstance(channels, list):
        return pairs
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        ch_name = ch.get("name", "")
        if not ch_name:
            continue
        for key in ("node1", "node2"):
            raw = ch.get(key, "")
            bare = raw.replace("前", "").replace("后", "").replace("入流", "").replace("出流", "")
            if bare:
                pairs.append((bare, ch_name))
        pairs.append((ch_name, ch_name))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs
