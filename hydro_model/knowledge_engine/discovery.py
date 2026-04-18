"""Universal file discovery engine.

Recursively scans configured directories, matches files against the
taxonomy's extension and filename pattern rules, then dispatches each
matched file to registered miners for extraction.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import hashlib
import zipfile
import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import GLOBAL_REGISTRY, MineResult, MinerRegistry
from .taxonomy import TYPE_CATALOG, DataType, TypeMeta, all_extensions
from .archive_extractor import ArchiveExtractor

log = logging.getLogger(__name__)


@dataclass
class FileCandidate:
    """A discovered file with potential data types."""
    path: Path
    rel_path: str
    size_bytes: int
    modified: str
    candidate_types: list[DataType] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    """Summary of a single discovery run."""
    case_id: str
    scan_dirs: list[str]
    timestamp: str = ""
    files_scanned: int = 0
    files_matched: int = 0
    results_by_type: dict[str, list[MineResult]] = field(default_factory=dict)
    coverage: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)


_MULTIPLEX_EXTENSIONS = frozenset({".json", ".sqlite3", ".db", ".yaml", ".yml", ".xlsx", ".xls"})


def _match_type(path: Path, meta: TypeMeta) -> bool:
    """Check if a file matches a TypeMeta by extension AND filename pattern.

    For multiplex formats (JSON, SQLite, YAML) the filename pattern is
    relaxed — these formats commonly embed many data types in one file,
    so we let the miner.probe decide what's actually inside.
    """
    ext = path.suffix.lower()
    if ext not in meta.extensions:
        return False
    if ext in _MULTIPLEX_EXTENSIONS:
        return True
    name_lower = path.name.lower()
    if not meta.filename_patterns:
        return True
    return any(fnmatch.fnmatch(name_lower, pat) for pat in meta.filename_patterns)


def _classify_file(path: Path) -> list[DataType]:
    """Return all DataTypes that *path* could belong to."""
    matches: list[DataType] = []
    for dt, meta in TYPE_CATALOG.items():
        if _match_type(path, meta):
            matches.append(dt)
    return matches


def scan_directories(
    scan_dirs: list[str],
    workspace: Path,
    *,
    skip_hidden: bool = True,
    max_file_size_mb: float = 500.0,
) -> list[FileCandidate]:
    """Recursively scan directories and classify every relevant file."""
    known_exts = all_extensions()
    candidates: list[FileCandidate] = []

    dirs_to_scan = []
    for raw_dir in scan_dirs:
        d = Path(raw_dir) if Path(raw_dir).is_absolute() else workspace / raw_dir
        if d.exists():
            dirs_to_scan.append(d)
        else:
            log.warning("scan dir does not exist: %s", d)

    scanned_dirs = set()
    
    while dirs_to_scan:
        current_dir = dirs_to_scan.pop(0)
        try:
            d_resolved = current_dir.resolve()
        except Exception:
            continue
            
        if d_resolved in scanned_dirs:
            continue
        scanned_dirs.add(d_resolved)
        
        for root, dirs, files in os.walk(current_dir):
            if skip_hidden:
                dirs[:] = [x for x in dirs if not x.startswith(".")]
            for fname in files:
                if skip_hidden and fname.startswith("."):
                    continue
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                
                if fpath.stat().st_size > max_file_size_mb * 1024 * 1024:
                    if not ArchiveExtractor.is_supported(fpath):
                        continue
                    elif fpath.stat().st_size > 10000.0 * 1024 * 1024:  # Hard limit 10GB for archives
                        continue
                    
                if ArchiveExtractor.is_supported(fpath):
                    cache_dir = ArchiveExtractor.extract(fpath, workspace)
                    if cache_dir:
                        dirs_to_scan.append(cache_dir)
                    continue

                if ext not in known_exts:
                    continue
                types = _classify_file(fpath)
                if not types:
                    continue
                try:
                    rel = str(fpath.relative_to(workspace))
                except ValueError:
                    rel = str(fpath)
                mtime = datetime.fromtimestamp(
                    fpath.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds")
                candidates.append(FileCandidate(
                    path=fpath,
                    rel_path=rel,
                    size_bytes=fpath.stat().st_size,
                    modified=mtime,
                    candidate_types=types,
                ))

    return candidates


def run_discovery(
    cfg: dict[str, Any],
    workspace: Path,
    *,
    registry: MinerRegistry | None = None,
    types_filter: list[DataType] | None = None,
) -> DiscoveryReport:
    """Full discovery pipeline: scan → classify → extract."""
    reg = registry or GLOBAL_REGISTRY
    case_id = cfg.get("case_id", "unknown")
    scan_dirs = cfg.get("scan_dirs", [])
    report = DiscoveryReport(
        case_id=case_id,
        scan_dirs=list(scan_dirs),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    candidates = scan_directories(scan_dirs, workspace)
    report.files_scanned = len(candidates)

    matched_count = 0
    for fc in candidates:
        for dt in fc.candidate_types:
            if types_filter and dt not in types_filter:
                continue
            miners = reg.miners_for(dt)
            if not miners:
                continue
            for miner in miners:
                try:
                    probed = miner.probe(fc.path, cfg)
                    if dt not in probed:
                        continue
                    results = miner.extract(fc.path, dt, cfg)
                    if results:
                        matched_count += 1
                        report.results_by_type.setdefault(dt.value, []).extend(results)
                except Exception as exc:
                    report.errors.append({
                        "file": fc.rel_path,
                        "data_type": dt.value,
                        "miner": type(miner).__name__,
                        "error": str(exc),
                    })
                    log.warning("miner error on %s: %s", fc.rel_path, exc)

    report.files_matched = matched_count
    report.coverage = {
        dt.value: len(report.results_by_type.get(dt.value, []))
        for dt in DataType
    }
    return report
