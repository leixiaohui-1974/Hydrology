import numpy as np
from .model import HydrologicalModel
from .runoff import SimpleRunoffModule
from .routing import SimpleRouting

class ParameterZone:
    """
    参数分区，包含一套水文模型参数。
    """
    def __init__(self, zone_id, params):
        self.zone_id = zone_id
        self.params = params

class SubBasin:
    """
    子流域，是模型计算的基本单元。
    """
    def __init__(self, pfaf_code, area, zone_id, downstream_pfaf=None):
        self.pfaf_code = pfaf_code
        self.area = area  # in km^2
        self.zone_id = zone_id
        self.downstream_pfaf = downstream_pfaf
        self.model = None
        self.inflow = 0.0

    def initialize_model(self, params):
        # Create instances of the modules based on the parameters
        runoff_module = SimpleRunoffModule(**params)
        routing_module = SimpleRouting(**params)
        # Compose them into the main model
        self.model = HydrologicalModel(runoff_module, routing_module)

class Catchment:
    """
    管理整个流域，包括所有子流域和参数分区。
    """
    def __init__(self):
        self.sub_basins = {}
        self.parameter_zones = {}
        self.simulation_order = []

    def add_parameter_zone(self, zone_id, params):
        self.parameter_zones[zone_id] = ParameterZone(zone_id, params)

    def add_sub_basin(self, pfaf_code, area, zone_id, downstream_pfaf=None):
        sub_basin = SubBasin(pfaf_code, area, zone_id, downstream_pfaf)
        params = self.parameter_zones[zone_id].params
        sub_basin.initialize_model(params)
        self.sub_basins[pfaf_code] = sub_basin

    def _determine_simulation_order(self):
        # 基于 Pfafstetter 编码排序，确保从上游到下游的计算顺序
        # 简单起见，我们直接按编码的字符串顺序排序，这在很多情况下是有效的
        self.simulation_order = sorted(self.sub_basins.keys(), reverse=True)

    def run_simulation(self, rainfall_data, pet_data):
        self._determine_simulation_order()

        # 从第一个降雨序列的长度获取时间步数
        first_pfaf_key = list(rainfall_data.keys())[0]
        num_steps = len(rainfall_data[first_pfaf_key])

        results = {pfaf: np.zeros(num_steps) for pfaf in self.sub_basins}
        inflows = {pfaf: np.zeros(num_steps) for pfaf in self.sub_basins}

        for t in range(num_steps):
            for pfaf_code in self.simulation_order:
                sub_basin = self.sub_basins[pfaf_code]

                # 获取当前子流域的降雨和蒸发
                # 假设 rainfall_data 和 pet_data 的 key 是 pfaf_code
                rainfall = rainfall_data[pfaf_code][t]
                pet = pet_data[pfaf_code][t]

                # 计算本地径流
                local_runoff_mm = sub_basin.model.run(rainfall, pet)
                local_runoff_m3s = (local_runoff_mm / 1000) * (sub_basin.area * 1e6) / (24 * 3600)

                # 获取上游来水
                upstream_inflow_m3s = inflows[pfaf_code][t]

                # 总出流量
                total_outflow_m3s = local_runoff_m3s + upstream_inflow_m3s
                results[pfaf_code][t] = total_outflow_m3s

                # 演算到下游
                if sub_basin.downstream_pfaf and (t + 1 < num_steps):
                    # 简单的滞后演算
                    lag_time_steps = 1 # 假设延迟一个时间步
                    if t + lag_time_steps < num_steps:
                        inflows[sub_basin.downstream_pfaf][t + lag_time_steps] += total_outflow_m3s

        return results
