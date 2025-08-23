import sys
import os
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.controller import SimulationController
from common.base_model import BaseModelComponent
from real_twin.diagnostic_engine import DiagnosticEngine

# --- WORKAROUND: Define SimplePassthroughModel here to avoid import issues ---
class SimplePassthroughModel(BaseModelComponent):
    def __init__(self, name: str, coeff: float = 1.0, **kwargs):
        super().__init__(name)
        self.coeff = coeff

    def step(self, inflows: dict, dt: float):
        rainfall = inflows.get('rainfall', 0.0)
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet', 'temperature', 'lateral_flow'])
        self.outflow = rainfall * self.coeff + upstream_inflow
# --- END WORKAROUND ---

def correct_data_with_idw(faulty_gauge_name, current_inputs, catchment_config, sensor_health):
    """
    Corrects data for a faulty gauge using Inverse Distance Weighting from healthy neighbors.
    """
    faulty_coords = None
    for c_data in catchment_config.values():
        if c_data.get('rain_gauge') == faulty_gauge_name:
            faulty_coords = c_data.get('coords')
            break

    if not faulty_coords:
        return current_inputs[faulty_gauge_name]

    healthy_gauges = []
    for c_data in catchment_config.values():
        gauge_name = c_data.get('rain_gauge')
        if gauge_name and sensor_health.get(gauge_name, 0) >= 50:
            healthy_gauges.append({
                'name': gauge_name,
                'coords': c_data.get('coords'),
                'value': current_inputs.get(gauge_name)
            })

    if not healthy_gauges:
        return current_inputs[faulty_gauge_name]

    numerator = 0
    denominator = 0
    power = 2

    for hg in healthy_gauges:
        dist = np.sqrt((faulty_coords[0] - hg['coords'][0])**2 + (faulty_coords[1] - hg['coords'][1])**2)
        if dist == 0: return hg['value']

        weight = 1 / (dist ** power)
        numerator += weight * hg['value']
        denominator += weight

    return numerator / denominator if denominator > 0 else current_inputs[faulty_gauge_name]


def main():
    """
    Main execution function for running the full Real-Twin simulation
    with an integrated online diagnostic engine and feedback loop.
    """
    print("--- Initializing Real-Twin Simulation ---")

    # 1. Load raw sensor data
    twin_rain_obs = pd.read_csv('examples/real_twin_framework/twin_rainfall.csv')
    twin_flow_obs = pd.read_csv('examples/real_twin_framework/twin_flow.csv')

    # 2. Manually create Controller and Components
    controller = SimulationController()
    c1 = SimplePassthroughModel(name='Catchment1')
    c2 = SimplePassthroughModel(name='Catchment2')
    c3 = SimplePassthroughModel(name='Catchment3')
    controller.add_component(c1)
    controller.add_component(c2)
    controller.add_component(c3)
    controller.connect('Catchment3', 'Catchment2')
    controller.connect('Catchment2', 'Catchment1')
    controller._detect_and_sort_components()

    # 3. Initialize Diagnostic Engine
    catchment_config = {
        'Catchment1': {'area_km2': 120, 'upstream': 'Catchment2', 'rain_gauge': 'RG1', 'flow_gauge': 'FG1', 'coords': (5, 5)},
        'Catchment2': {'area_km2': 200, 'upstream': 'Catchment3', 'rain_gauge': 'RG2', 'flow_gauge': 'FG2', 'coords': (5, 15)},
        'Catchment3': {'area_km2': 150, 'upstream': None, 'rain_gauge': 'RG3', 'flow_gauge': None, 'coords': (15, 10)}
    }
    general_diag_config = {
        'downstream_gauges': ['FG1', 'FG2'],
        'controlling_gauges': ['RG1', 'RG2', 'RG3']
    }
    engine = DiagnosticEngine(catchment_config, general_diag_config)

    # 4. Run the simulation loop
    num_steps = 30
    controller.results = {name: [] for name in controller.components}
    output_data = []

    print("\n--- Running Real-Twin Simulation with Feedback Loop ---")
    for t in range(num_steps):
        current_inputs = {col: twin_rain_obs[col].iloc[t] for col in twin_rain_obs.columns if col != 'time_step'}
        current_inputs.update({col: twin_flow_obs[col].iloc[t] for col in twin_flow_obs.columns if col != 'time_step'})

        engine.run_step(t, current_inputs, controller.results)

        corrected_inputs = current_inputs.copy()
        for gauge, health in engine.sensor_health.items():
            if health < 50:
                corrected_value = correct_data_with_idw(gauge, corrected_inputs, catchment_config, engine.sensor_health)
                print(f"  CORRECTION: Replacing {gauge} value ({corrected_inputs[gauge]:.2f}) with IDW value ({corrected_value:.2f})")
                corrected_inputs[gauge] = corrected_value

        for comp_name in controller.execution_order:
            inflows = {}
            if comp_name == 'Catchment1': inflows['rainfall'] = corrected_inputs.get('RG1', 0)
            if comp_name == 'Catchment2': inflows['rainfall'] = corrected_inputs.get('RG2', 0)
            if comp_name == 'Catchment3': inflows['rainfall'] = corrected_inputs.get('RG3', 0)

            parent_names = controller.parents.get(comp_name, [])
            for parent_name in parent_names:
                inflows[parent_name] = controller.components[parent_name].get_outflow()

            controller.components[comp_name].step(inflows, 86400)

        step_results = {'time_step': t}
        for name, component in controller.components.items():
            outflow = component.get_outflow()
            controller.results[name].append(outflow)
            step_results[f'sim_{name}'] = outflow

        step_results.update({f'health_{k}': v for k, v in engine.sensor_health.items()})
        step_results['reliability_index'] = engine.reliability_index
        step_results['raw_RG2'] = current_inputs.get('RG2')
        step_results['corrected_RG2'] = corrected_inputs.get('RG2')
        output_data.append(step_results)

    print("\n--- Real-Twin Simulation Finished ---")

    final_df = pd.DataFrame(output_data).set_index('time_step')
    final_output_path = 'examples/real_twin_framework/final_results.csv'
    final_df.to_csv(final_output_path)
    print(f"Final simulation results with diagnostics saved to {final_output_path}")

if __name__ == "__main__":
    main()
