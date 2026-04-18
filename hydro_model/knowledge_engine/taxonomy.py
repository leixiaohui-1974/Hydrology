"""Data type taxonomy — 6 domains, 27 subtypes.

Every data type consumed or produced by any workflow is classified here.
Miners register against these types; the discovery engine routes files
to the correct miner based on type metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique


@unique
class Domain(str, Enum):
    GEOSPATIAL = "geospatial"
    INFRASTRUCTURE = "infrastructure"
    STATIONS = "stations"
    TOPOLOGY = "topology"
    HYDRAULIC = "hydraulic"
    TIMESERIES = "timeseries"


@unique
class DataType(str, Enum):
    # A. GeoSpatial
    DEM = "A1_dem"
    LAND_USE = "A2_land_use"
    SOIL = "A3_soil"
    BASIN_BOUNDARY = "A4_basin_boundary"
    RIVER_NETWORK = "A5_river_network"

    # B. Infrastructure
    RESERVOIR = "B1_reservoir"
    HYDROPOWER_STATION = "B2_hydropower_station"
    TURBINE = "B3_turbine"
    GATE = "B4_gate"
    PUMP_VALVE = "B5_pump_valve"

    # C. Stations
    HYDRO_STATION = "C1_hydro_station"
    RAINFALL_STATION = "C2_rainfall_station"
    EVAP_STATION = "C3_evap_station"
    STATION_CONTROL_AREA = "C4_station_control_area"

    # D. Topology
    RIVER_TOPO = "D1_river_topo"
    BASIN_TOPO = "D2_basin_topo"
    STATION_BASIN_REL = "D3_station_basin_rel"
    CASCADE_ARRANGEMENT = "D4_cascade_arrangement"

    # E. Hydraulic
    CROSS_SECTION = "E1_cross_section"
    MANNING_ROUGHNESS = "E2_manning_roughness"
    ZV_CURVE = "E3_zv_curve"
    ZQ_CURVE = "E4_zq_curve"
    FLOW_CURVE = "E5_flow_curve"

    # F. Time Series
    TS_RAINFALL = "F1_rainfall"
    TS_WATER_LEVEL = "F2_water_level"
    TS_DISCHARGE = "F3_discharge"
    TS_EVAPORATION = "F4_evaporation"
    TS_METEOROLOGICAL = "F5_meteorological"


DOMAIN_OF: dict[DataType, Domain] = {
    DataType.DEM: Domain.GEOSPATIAL,
    DataType.LAND_USE: Domain.GEOSPATIAL,
    DataType.SOIL: Domain.GEOSPATIAL,
    DataType.BASIN_BOUNDARY: Domain.GEOSPATIAL,
    DataType.RIVER_NETWORK: Domain.GEOSPATIAL,
    DataType.RESERVOIR: Domain.INFRASTRUCTURE,
    DataType.HYDROPOWER_STATION: Domain.INFRASTRUCTURE,
    DataType.TURBINE: Domain.INFRASTRUCTURE,
    DataType.GATE: Domain.INFRASTRUCTURE,
    DataType.PUMP_VALVE: Domain.INFRASTRUCTURE,
    DataType.HYDRO_STATION: Domain.STATIONS,
    DataType.RAINFALL_STATION: Domain.STATIONS,
    DataType.EVAP_STATION: Domain.STATIONS,
    DataType.STATION_CONTROL_AREA: Domain.STATIONS,
    DataType.RIVER_TOPO: Domain.TOPOLOGY,
    DataType.BASIN_TOPO: Domain.TOPOLOGY,
    DataType.STATION_BASIN_REL: Domain.TOPOLOGY,
    DataType.CASCADE_ARRANGEMENT: Domain.TOPOLOGY,
    DataType.CROSS_SECTION: Domain.HYDRAULIC,
    DataType.MANNING_ROUGHNESS: Domain.HYDRAULIC,
    DataType.ZV_CURVE: Domain.HYDRAULIC,
    DataType.ZQ_CURVE: Domain.HYDRAULIC,
    DataType.FLOW_CURVE: Domain.HYDRAULIC,
    DataType.TS_RAINFALL: Domain.TIMESERIES,
    DataType.TS_WATER_LEVEL: Domain.TIMESERIES,
    DataType.TS_DISCHARGE: Domain.TIMESERIES,
    DataType.TS_EVAPORATION: Domain.TIMESERIES,
    DataType.TS_METEOROLOGICAL: Domain.TIMESERIES,
}


@dataclass(frozen=True)
class TypeMeta:
    """Metadata descriptor for a DataType."""
    data_type: DataType
    domain: Domain
    label_cn: str
    extensions: tuple[str, ...] = ()
    filename_patterns: tuple[str, ...] = ()
    knowledge_path: str = ""
    required: bool = False


TYPE_CATALOG: dict[DataType, TypeMeta] = {
    # --- A. GeoSpatial ---
    DataType.DEM: TypeMeta(
        DataType.DEM, Domain.GEOSPATIAL, "数字高程模型",
        extensions=(".tif", ".tiff", ".asc", ".hgt"),
        filename_patterns=("*dem*", "*srtm*", "*aster*", "*elevation*"),
        knowledge_path="terrain/dem_strategy.yaml",
        required=True,
    ),
    DataType.LAND_USE: TypeMeta(
        DataType.LAND_USE, Domain.GEOSPATIAL, "土地利用",
        extensions=(".tif", ".tiff", ".shp"),
        filename_patterns=("*land*use*", "*土地*利用*", "*landcover*", "*LULC*"),
        knowledge_path="geospatial/land_use.yaml",
    ),
    DataType.SOIL: TypeMeta(
        DataType.SOIL, Domain.GEOSPATIAL, "土壤类型",
        extensions=(".tif", ".tiff", ".shp"),
        filename_patterns=("*soil*", "*土壤*", "*HWSD*"),
        knowledge_path="geospatial/soil.yaml",
    ),
    DataType.BASIN_BOUNDARY: TypeMeta(
        DataType.BASIN_BOUNDARY, Domain.GEOSPATIAL, "流域边界",
        extensions=(".shp", ".geojson", ".gpkg"),
        filename_patterns=("*basin*", "*流域*", "*catchment*", "*watershed*"),
        knowledge_path="geospatial/basin_boundary.yaml",
    ),
    DataType.RIVER_NETWORK: TypeMeta(
        DataType.RIVER_NETWORK, Domain.GEOSPATIAL, "河网水系",
        extensions=(".shp", ".geojson", ".gpkg"),
        filename_patterns=("*river*", "*河网*", "*水系*", "*hydrorivers*", "*stream*"),
        knowledge_path="geospatial/river_network.yaml",
        required=True,
    ),
    # --- B. Infrastructure ---
    DataType.RESERVOIR: TypeMeta(
        DataType.RESERVOIR, Domain.INFRASTRUCTURE, "水库",
        extensions=(".json", ".yaml", ".csv", ".xlsx"),
        filename_patterns=("*水库*", "*reservoir*", "*库容*"),
        knowledge_path="topology/reservoirs.yaml",
        required=True,
    ),
    DataType.HYDROPOWER_STATION: TypeMeta(
        DataType.HYDROPOWER_STATION, Domain.INFRASTRUCTURE, "水电站",
        extensions=(".json", ".yaml", ".csv", ".xlsx"),
        filename_patterns=("*水电站*", "*hydropower*", "*电站*", "*装机*"),
        knowledge_path="infrastructure/hydropower.yaml",
    ),
    DataType.TURBINE: TypeMeta(
        DataType.TURBINE, Domain.INFRASTRUCTURE, "水轮机",
        extensions=(".json", ".yaml"),
        filename_patterns=("*水轮机*", "*turbine*", "*机组*"),
        knowledge_path="topology/turbines.yaml",
        required=True,
    ),
    DataType.GATE: TypeMeta(
        DataType.GATE, Domain.INFRASTRUCTURE, "闸门",
        extensions=(".json", ".yaml"),
        filename_patterns=("*闸*", "*gate*", "*泄洪*"),
        knowledge_path="topology/gates.yaml",
        required=True,
    ),
    DataType.PUMP_VALVE: TypeMeta(
        DataType.PUMP_VALVE, Domain.INFRASTRUCTURE, "泵阀",
        extensions=(".json", ".yaml", ".csv"),
        filename_patterns=("*泵*", "*阀*", "*pump*", "*valve*"),
        knowledge_path="infrastructure/pump_valve.yaml",
    ),
    # --- C. Stations ---
    DataType.HYDRO_STATION: TypeMeta(
        DataType.HYDRO_STATION, Domain.STATIONS, "水文站",
        extensions=(".json", ".csv", ".sqlite3", ".db", ".xlsx"),
        filename_patterns=("*水文站*", "*hydro*station*", "*站点*"),
        knowledge_path="stations/hydro_stations.yaml",
        required=True,
    ),
    DataType.RAINFALL_STATION: TypeMeta(
        DataType.RAINFALL_STATION, Domain.STATIONS, "雨量站",
        extensions=(".json", ".csv", ".sqlite3", ".db", ".xlsx"),
        filename_patterns=("*雨量站*", "*rainfall*station*", "*雨量*"),
        knowledge_path="stations/rainfall_stations.yaml",
    ),
    DataType.EVAP_STATION: TypeMeta(
        DataType.EVAP_STATION, Domain.STATIONS, "蒸发站",
        extensions=(".json", ".csv", ".xlsx"),
        filename_patterns=("*蒸发*", "*evap*"),
        knowledge_path="stations/evap_stations.yaml",
    ),
    DataType.STATION_CONTROL_AREA: TypeMeta(
        DataType.STATION_CONTROL_AREA, Domain.STATIONS, "站点控制流域面积",
        extensions=(".json", ".csv", ".yaml", ".xlsx"),
        filename_patterns=("*控制面积*", "*catchment_area*", "*Amin*", "*basin_area*"),
        knowledge_path="stations/control_areas.yaml",
        required=True,
    ),
    # --- D. Topology ---
    DataType.RIVER_TOPO: TypeMeta(
        DataType.RIVER_TOPO, Domain.TOPOLOGY, "河网拓扑",
        extensions=(".json", ".yaml"),
        filename_patterns=("*拓扑*", "*topology*", "*智能体*", "*model*"),
        knowledge_path="topology/topology.yaml",
        required=True,
    ),
    DataType.BASIN_TOPO: TypeMeta(
        DataType.BASIN_TOPO, Domain.TOPOLOGY, "流域拓扑",
        extensions=(".json", ".yaml", ".shp"),
        filename_patterns=("*流域拓扑*", "*basin_topo*", "*sub*basin*"),
        knowledge_path="topology/basin_topo.yaml",
    ),
    DataType.STATION_BASIN_REL: TypeMeta(
        DataType.STATION_BASIN_REL, Domain.TOPOLOGY, "站点-流域关系",
        extensions=(".json", ".yaml", ".csv"),
        filename_patterns=("*站点*流域*", "*station*basin*"),
        knowledge_path="topology/station_basin_rel.yaml",
    ),
    DataType.CASCADE_ARRANGEMENT: TypeMeta(
        DataType.CASCADE_ARRANGEMENT, Domain.TOPOLOGY, "梯级排列",
        extensions=(".json", ".yaml"),
        filename_patterns=("*梯级*", "*cascade*", "*级联*"),
        knowledge_path="topology/cascade.yaml",
        required=True,
    ),
    # --- E. Hydraulic ---
    DataType.CROSS_SECTION: TypeMeta(
        DataType.CROSS_SECTION, Domain.HYDRAULIC, "河道断面",
        extensions=(".txt", ".json", ".xlsx", ".canal"),
        filename_patterns=("*断面*", "*地形*", "*section*", "*terrain*", "*cross*"),
        knowledge_path="topology/sections.yaml",
        required=True,
    ),
    DataType.MANNING_ROUGHNESS: TypeMeta(
        DataType.MANNING_ROUGHNESS, Domain.HYDRAULIC, "河道糙率",
        extensions=(".json", ".yaml", ".csv"),
        filename_patterns=("*糙率*", "*manning*", "*roughness*"),
        knowledge_path="params/hydraulics.yaml",
        required=True,
    ),
    DataType.ZV_CURVE: TypeMeta(
        DataType.ZV_CURVE, Domain.HYDRAULIC, "水位-库容曲线",
        extensions=(".txt", ".csv", ".json", ".xlsx", ".xls"),
        filename_patterns=("*库容*", "*ZV*", "*水位*容*", "*storage*"),
        knowledge_path="curves/zv_curves.yaml",
        required=True,
    ),
    DataType.ZQ_CURVE: TypeMeta(
        DataType.ZQ_CURVE, Domain.HYDRAULIC, "水位-流量曲线",
        extensions=(".txt", ".csv", ".json", ".xlsx", ".xls"),
        filename_patterns=("*水位*流量*", "*ZQ*", "*rating*curve*", "*关系曲线*"),
        knowledge_path="curves/zq_curves.yaml",
    ),
    DataType.FLOW_CURVE: TypeMeta(
        DataType.FLOW_CURVE, Domain.HYDRAULIC, "过流曲线",
        extensions=(".json", ".yaml", ".csv"),
        filename_patterns=("*过流*", "*discharge*curve*", "*泄流*"),
        knowledge_path="curves/flow_curves.yaml",
    ),
    # --- F. Time Series ---
    DataType.TS_RAINFALL: TypeMeta(
        DataType.TS_RAINFALL, Domain.TIMESERIES, "降雨时间序列",
        extensions=(".csv", ".tsv", ".sqlite3", ".db", ".txt", ".xlsx", ".xls"),
        filename_patterns=("*雨量*", "*降雨*", "*rainfall*", "*precip*", "*P_total*"),
        knowledge_path="timeseries/rainfall.yaml",
        required=True,
    ),
    DataType.TS_WATER_LEVEL: TypeMeta(
        DataType.TS_WATER_LEVEL, Domain.TIMESERIES, "水位时间序列",
        extensions=(".csv", ".tsv", ".sqlite3", ".db", ".txt", ".xlsx", ".xls"),
        filename_patterns=("*水位*", "*water*level*", "*H_up*", "*H_down*", "*waterLevel*"),
        knowledge_path="timeseries/water_level.yaml",
        required=True,
    ),
    DataType.TS_DISCHARGE: TypeMeta(
        DataType.TS_DISCHARGE, Domain.TIMESERIES, "流量时间序列",
        extensions=(".csv", ".tsv", ".sqlite3", ".db", ".txt", ".xlsx", ".xls"),
        filename_patterns=("*流量*", "*discharge*", "*Q_out*", "*Q_in*", "*streamflow*"),
        knowledge_path="timeseries/discharge.yaml",
        required=True,
    ),
    DataType.TS_EVAPORATION: TypeMeta(
        DataType.TS_EVAPORATION, Domain.TIMESERIES, "蒸发时间序列",
        extensions=(".csv", ".tsv", ".sqlite3", ".db", ".txt", ".xlsx", ".xls"),
        filename_patterns=("*蒸发*", "*evap*", "*E_pan*"),
        knowledge_path="timeseries/evaporation.yaml",
    ),
    DataType.TS_METEOROLOGICAL: TypeMeta(
        DataType.TS_METEOROLOGICAL, Domain.TIMESERIES, "气象时间序列",
        extensions=(".csv", ".tsv", ".sqlite3", ".db", ".txt", ".xlsx", ".xls"),
        filename_patterns=("*气温*", "*温度*", "*wind*", "*humidity*", "*temperature*", "*meteo*"),
        knowledge_path="timeseries/meteorological.yaml",
    ),
}


def types_in_domain(domain: Domain) -> list[DataType]:
    return [dt for dt, d in DOMAIN_OF.items() if d == domain]


def required_types() -> list[DataType]:
    return [dt for dt, m in TYPE_CATALOG.items() if m.required]


def all_extensions() -> set[str]:
    exts: set[str] = set()
    for m in TYPE_CATALOG.values():
        exts.update(m.extensions)
    return exts
