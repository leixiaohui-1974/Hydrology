from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = BASE_DIR.parent

_results_override = os.environ.get("HYDROLOGY_RESULTS_DIR")
RESULTS_DIR = Path(_results_override) if _results_override else BASE_DIR / "examples" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def coerce_path_str(raw: Any) -> str | None:
    """YAML 中路径项可能是字符串或 ``{path: ...}`` 等字典，统一为可解析的路径字符串。"""
    if isinstance(raw, (str, Path)):
        s = str(raw).strip()
        return s or None
    if isinstance(raw, dict):
        for k in ("path", "file", "sqlite", "db_path", "database"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def resolve_workspace_relpath(raw: str | Path) -> Path:
    """Resolve a path; if relative, interpret from WORKSPACE (monorepo root)."""
    p = Path(raw)
    if p.is_absolute():
        try:
            return p.resolve()
        except RuntimeError:
            return p.absolute()
    target = WORKSPACE / p
    try:
        return target.resolve()
    except RuntimeError:
        return target.absolute()


def _safe_absolute(path: Path) -> Path:
    try:
        return path.resolve()
    except RuntimeError:
        return path.absolute()


def _workspace_rel(path: Path) -> str:
    return _safe_absolute(path).relative_to(_safe_absolute(WORKSPACE)).as_posix()


def _is_workspace_local_path(path: Path) -> bool:
    try:
        _safe_absolute(path).relative_to(_safe_absolute(WORKSPACE))
        return True
    except ValueError:
        return False


def _redacted_external_path(path: Path) -> str:
    name = path.name or "unknown"
    return f"[external]/{name}"


def persisted_path_or_none(path: Path | None) -> str | None:
    if path is None:
        return None
    if _is_workspace_local_path(path):
        return _workspace_rel(path)
    return _redacted_external_path(path)


def persisted_raw_path_or_none(raw_path: Any) -> str | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    if text.startswith("[external]/"):
        return text
    try:
        path = resolve_workspace_relpath(text)
    except Exception:
        return text
    if Path(text).is_absolute():
        return persisted_path_or_none(path) or text
    if _is_workspace_local_path(path):
        return _workspace_rel(path)
    return text


def normalize_serialized_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_serialized_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_serialized_paths(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_serialized_paths(item) for item in value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.startswith("[external]/"):
            return value
        if Path(text).is_absolute():
            return persisted_raw_path_or_none(text) or value
    return value


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


def _safe_load_json(path: Path) -> Any:
    try:
        return load_json(path)
    except Exception:
        return {}


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
    else:
        kb = load_knowledge(case_id, config_path)
        if kb:
            # Only update keys that are not already present or merge dicts
            for k, v in kb.items():
                if k not in cfg["knowledge"] or not cfg["knowledge"][k]:
                    cfg["knowledge"][k] = v

    return cfg


def load_case_manifest(case_id: str, manifest_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Load a case manifest YAML; default to cases/<case_id>/manifest.yaml."""
    if manifest_path:
        path = resolve_workspace_relpath(manifest_path)
    else:
        path = WORKSPACE / "cases" / case_id / "manifest.yaml"
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return path.resolve(), payload

    fallback = WORKSPACE / "cases" / case_id / "contracts" / "case_manifest.json"
    if fallback.exists():
        payload = _safe_load_json(fallback)
        return fallback.resolve(), payload if isinstance(payload, dict) else {}
    return path, {}


def default_graphify_case_sidecar_dir(case_id: str) -> Path:
    return WORKSPACE / ".graphify" / "pilots" / f"case-{case_id}" / "graphify-out"


def first_existing_workspace_path(candidates: list[str | Path | None]) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        resolved = resolve_workspace_relpath(candidate)
        if resolved.exists():
            return resolved
    return None


def _load_case_data_pack(case_id: str) -> dict[str, Any]:
    contracts_dir = WORKSPACE / "cases" / case_id / "contracts"
    for name in ("data_pack.latest.json", "data_pack.contract.json", "data_pack.v2.json", "data_pack.json"):
        path = contracts_dir / name
        if not path.exists():
            continue
        try:
            payload = load_json(path)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def _path_from_data_pack(payload: dict[str, Any], key: str) -> Path | None:
    raw = str(payload.get(key) or "").strip()
    if not raw:
        return None
    resolved = resolve_workspace_relpath(raw)
    return resolved if resolved.exists() else None


def _first_existing_with_source(candidates: list[tuple[str, str | Path | None]]) -> tuple[Path | None, str]:
    for source, candidate in candidates:
        if not candidate:
            continue
        resolved = resolve_workspace_relpath(candidate)
        if resolved.exists():
            return resolved, source
    return None, "missing"


def _outlets_contract_has_points(path: Path) -> bool:
    """True if JSON contains a non-empty outlet list (object.outlets or top-level list)."""
    try:
        payload = load_json(path)
    except Exception:
        return False
    raw = payload.get("outlets", payload) if isinstance(payload, dict) else payload
    return isinstance(raw, list) and len(raw) > 0


def resolve_case_entry_inputs(
    case_id: str,
    *,
    case_manifest: str | Path | None = None,
    source_bundle_json: str | Path | None = None,
    outlets_json: str | Path | None = None,
    simulation_config: str | Path | None = None,
) -> dict[str, str | None]:
    """Resolve the minimal inputs needed by the case pipeline entrypoint.

    Precedence:
    1. Explicit CLI value
    2. `cases/<id>/manifest.yaml` latest_* slots
    3. Case config (`Hydrology/configs/<id>.yaml`) and standard contracts / product_outputs paths
    4. Existing `data_pack*.json` pointers inside `cases/<id>/contracts`
    """
    manifest_path, manifest_payload = load_case_manifest(case_id, case_manifest)
    cfg = load_case_config(case_id)
    output_dir = cfg.get("output_dir")
    data_pack_payload = _load_case_data_pack(case_id)

    def _from_manifest(block_key: str) -> Path | None:
        block = manifest_payload.get(block_key) or {}
        raw = str(block.get("path") or "").strip()
        if not raw:
            return None
        resolved = resolve_workspace_relpath(raw)
        return resolved if resolved.exists() else None

    source_bundle, source_bundle_source = _first_existing_with_source(
        [
            ("explicit", source_bundle_json),
            ("manifest_latest", _from_manifest("latest_source_bundle")),
            ("case_config", cfg.get("source_bundle_path")),
            ("contracts_default", f"cases/{case_id}/contracts/source_bundle.contract.json"),
            ("contracts_legacy", f"cases/{case_id}/contracts/source_bundle.json"),
            ("data_pack_pointer", _path_from_data_pack(data_pack_payload, "source_bundle_json")),
        ]
    )
    source_bundle_sibling_outlets = source_bundle.parent / "outlets.normalized.json" if source_bundle else None
    outlet_candidates: list[tuple[str, str | Path | None]] = [
        ("explicit", outlets_json),
        ("manifest_latest", _from_manifest("latest_outlets")),
        ("contracts_default", f"cases/{case_id}/contracts/outlets.normalized.json"),
        ("source_bundle_sibling", source_bundle_sibling_outlets),
        ("product_outputs", Path(output_dir) / "outlets.delineation_ready.json" if output_dir else None),
        ("data_pack_pointer", _path_from_data_pack(data_pack_payload, "outlets_json")),
    ]
    outlets: Path | None = None
    outlets_source = "missing"
    for source, candidate in outlet_candidates:
        if not candidate:
            continue
        resolved = resolve_workspace_relpath(candidate)
        if resolved.exists() and _outlets_contract_has_points(resolved):
            outlets = resolved
            outlets_source = source
            break
    if outlets is None:
        outlets, outlets_source = _first_existing_with_source(outlet_candidates)
    sim_cfg, simulation_config_source = _first_existing_with_source(
        [
            ("explicit", simulation_config),
            ("case_config", BASE_DIR / "configs" / f"{case_id}.yaml"),
        ]
    )

    return {
        "case_manifest": persisted_path_or_none(manifest_path),
        "case_manifest_source": "explicit" if case_manifest else "default_manifest",
        "source_bundle_json": persisted_path_or_none(source_bundle),
        "source_bundle_source": source_bundle_source,
        "outlets_json": persisted_path_or_none(outlets),
        "outlets_source": outlets_source,
        "simulation_config": persisted_path_or_none(sim_cfg),
        "simulation_config_source": simulation_config_source,
    }


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
            target = workspace / val
            try:
                cfg[key] = str(target.resolve())
            except RuntimeError:
                cfg[key] = str(target.absolute())

    for key in list_path_keys:
        items = cfg.get(key, [])
        resolved = []
        for item in items:
            if item and not Path(item).is_absolute():
                target = workspace / item
                try:
                    resolved.append(str(target.resolve()))
                except RuntimeError:
                    resolved.append(str(target.absolute()))
            else:
                resolved.append(item)
        if resolved:
            cfg[key] = resolved

    return cfg



def is_sqlite_path_str(path_str: str) -> bool:
    low = path_str.lower()
    return low.endswith(".sqlite3") or low.endswith(".sqlite") or low.endswith(".db")



def resolve_sqlite_candidate_paths(
    cfg: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> tuple[list[Path], list[str], list[Path]]:
    explicit_candidates: list[Path] = []
    invalid_explicit_assets: list[str] = []
    scanned_candidates: list[Path] = []

    def _resolve_path(raw: str | Path) -> Path:
        path = Path(raw)
        if path.is_absolute():
            return path.resolve()
        base_dir = workspace if workspace is not None else WORKSPACE
        return (base_dir / path).resolve()

    for raw in cfg.get("sqlite_paths", []) or []:
        p = coerce_path_str(raw)
        if not p:
            continue
        path = _resolve_path(p)
        if not path.exists() or not path.is_file():
            continue
        if is_sqlite_path_str(str(path)):
            explicit_candidates.append(path)
        else:
            invalid_explicit_assets.append(str(path))

    scada_files = cfg.get("knowledge", {}).get("scada_timeseries", {}).get("files", []) or []
    for raw in scada_files:
        p = coerce_path_str(raw)
        if not p:
            continue
        path = _resolve_path(p)
        if path.exists() and path.is_file() and is_sqlite_path_str(str(path)):
            explicit_candidates.append(path)

    for scan_dir in cfg.get("scan_dirs", []) or []:
        scan_path = _resolve_path(str(scan_dir))
        if not scan_path.exists() or not scan_path.is_dir():
            continue
        for pattern in ("*.sqlite3", "*.sqlite", "*.db"):
            for file_path in sorted(scan_path.glob(pattern)):
                if file_path.is_file():
                    scanned_candidates.append(file_path.resolve())

    return explicit_candidates, invalid_explicit_assets, scanned_candidates



def sqlite_table_names(path: Path) -> list[str] | None:
    try:
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return [str(row[0]) for row in rows]


def sqlite_table_columns(path: Path, table_name: str) -> set[str] | None:
    try:
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return {str(row[1]) for row in rows if len(row) > 1 and row[1]}



def select_preferred_sqlite(
    cfg: dict[str, Any],
    *,
    schema_support_fn: Callable[[Path], bool],
    workspace: Path | None = None,
    allow_unsupported_fallback: bool = False,
) -> tuple[str | None, list[str]]:
    explicit_candidates, invalid_explicit_assets, scanned_candidates = resolve_sqlite_candidate_paths(
        cfg,
        workspace=workspace,
    )

    seen: set[str] = set()
    ordered_candidates: list[Path] = []
    for path in [*explicit_candidates, *scanned_candidates]:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered_candidates.append(path)

    fallback_db: str | None = None
    for path in ordered_candidates:
        table_names = sqlite_table_names(path)
        if table_names is None:
            if str(path) not in invalid_explicit_assets and path in explicit_candidates:
                invalid_explicit_assets.append(str(path))
            continue
        if schema_support_fn(path):
            return str(path), invalid_explicit_assets
        if allow_unsupported_fallback and fallback_db is None:
            fallback_db = str(path)

    return fallback_db, invalid_explicit_assets


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
        result = run_knowledge_mining("<case_id>")
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
