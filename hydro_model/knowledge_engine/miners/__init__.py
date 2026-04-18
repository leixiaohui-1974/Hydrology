"""Auto-register all built-in miners on import."""
from __future__ import annotations

from ..registry import register_miner
from .geospatial import GeoSpatialMiner
from .hydraulic import HydraulicMiner
from .infrastructure import InfrastructureMiner
from .stations import StationsMiner
from .timeseries import TimeseriesMiner
from .topology import TopologyMiner

_BUILTIN_MINERS = [
    GeoSpatialMiner(),
    InfrastructureMiner(),
    StationsMiner(),
    TopologyMiner(),
    HydraulicMiner(),
    TimeseriesMiner(),
]

for _m in _BUILTIN_MINERS:
    register_miner(_m)
