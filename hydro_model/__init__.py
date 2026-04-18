from .model import HydrologicalModel
from .runoff import SCSCurveNumberModule, SimpleRunoffModule
from .routing import SimpleRouting, MuskingumRouting, MuskingumCungeRouting, UnitHydrographRouting
from .catchment import Catchment
from .enkf import EnsembleKalmanFilter
from .parameter_zone import ParameterZone
from .reservoir_balance import ReservoirBalanceModel, calibrate_station
from .report_md import ReportGenerator

def __getattr__(name):
    """延迟导入重量级模块。"""
    if name in ("TerrainAnalyzer", "DEMData", "SubBasin", "WatershedResult", "FlowDirectionResult"):
        from .terrain_analysis import TerrainAnalyzer, DEMData, SubBasin, WatershedResult, FlowDirectionResult
        return locals()[name]
    if name == "DEMPipeline":
        from .dem_pipeline import DEMPipeline
        return DEMPipeline
    if name == "section_analysis":
        from . import section_analysis
        return section_analysis
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
