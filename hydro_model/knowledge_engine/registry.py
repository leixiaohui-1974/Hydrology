"""Miner registry — pluggable data-type miners with auto-registration.

Each concrete miner declares the DataTypes it handles.  The registry
maps DataType → miner instance so the discovery engine can dispatch
files to the correct extractor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .taxonomy import DataType

log = logging.getLogger(__name__)


# ── Miner protocol ──────────────────────────────────────────────────────────

@dataclass
class MineResult:
    """A single piece of mined knowledge."""
    data_type: DataType
    source_path: str
    source_kind: str          # json / csv / sqlite / raster / shapefile / ...
    payload: dict[str, Any]   # type-specific extracted data
    confidence: float = 0.0   # 0-1 quality score assigned by miner
    label: str = ""           # human-readable summary


@runtime_checkable
class Miner(Protocol):
    """Protocol every data miner must satisfy."""

    @property
    def handled_types(self) -> list[DataType]:
        """DataTypes this miner can extract."""
        ...

    def probe(self, path: Path, cfg: dict[str, Any]) -> list[DataType]:
        """Quick check: which handled types could *path* contain?

        Should be cheap (file extension / name pattern check only).
        Return empty list if path is irrelevant.
        """
        ...

    def extract(
        self, path: Path, data_type: DataType, cfg: dict[str, Any],
    ) -> list[MineResult]:
        """Full extraction from *path* for the given data_type.

        May do heavier I/O (read file, parse contents).
        Return zero or more MineResult items.
        """
        ...


# ── Registry singleton ──────────────────────────────────────────────────────

class MinerRegistry:
    """Central registry mapping DataType → Miner."""

    def __init__(self) -> None:
        self._miners: dict[DataType, list[Miner]] = {}

    def register(self, miner: Miner) -> None:
        for dt in miner.handled_types:
            self._miners.setdefault(dt, []).append(miner)
            log.debug("registered miner %s for %s", type(miner).__name__, dt.value)

    def miners_for(self, data_type: DataType) -> list[Miner]:
        return list(self._miners.get(data_type, []))

    def all_miners(self) -> list[Miner]:
        seen: set[int] = set()
        result: list[Miner] = []
        for miners in self._miners.values():
            for m in miners:
                mid = id(m)
                if mid not in seen:
                    seen.add(mid)
                    result.append(m)
        return result

    @property
    def registered_types(self) -> set[DataType]:
        return set(self._miners.keys())

    def coverage_report(self) -> dict[str, Any]:
        from .taxonomy import TYPE_CATALOG
        covered = self.registered_types
        missing = [dt.value for dt in TYPE_CATALOG if dt not in covered]
        return {
            "total_types": len(TYPE_CATALOG),
            "covered": len(covered),
            "missing_count": len(missing),
            "missing": missing,
        }


GLOBAL_REGISTRY = MinerRegistry()


def register_miner(miner: Miner) -> None:
    """Register a miner in the global registry."""
    GLOBAL_REGISTRY.register(miner)


def get_registry() -> MinerRegistry:
    return GLOBAL_REGISTRY
