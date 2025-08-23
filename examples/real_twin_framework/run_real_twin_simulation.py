import sys
import os
import pandas as pd

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.config_parser import ConfigParser
from real_twin.diagnostic_engine import DiagnosticEngine

def main():
    """
    Main execution function for running the full Real-Twin simulation
    with an integrated online diagnostic engine and feedback loop.
    """
    print("--- Initializing Real-Twin Simulation ---")

    # 1. Load configuration and raw sensor data
    config_file = 'examples/real_twin_framework/config_ground_truth.yaml'
    twin_rain_obs = pd.read_csv('examples/real_twin_framework/twin_rainfall.csv')
    twin_flow_obs = pd.read_csv('examples/real_twin_framework/twin_flow.csv')

    # 2. Initialize Controller and Diagnostic Engine
    parser = ConfigParser(config_file)
    controller, sim_params, _ = parser.build_simulation()

    catchment_config = {
        'Catchment1': {'area_km2': 120, 'upstream': 'Catchment2', 'rain_gauge': 'RG1', 'flow_gauge': 'FG1'},
        'Catchment2': {'area_km2': 200, 'upstream': 'Catchment3', 'rain_gauge': 'RG2', 'flow_gauge': 'FG2'},
        'Catchment3': {'area_km2': 150, 'upstream': None, 'rain_gauge': 'RG3', 'flow_gauge': None}
    }
    engine = DiagnosticEngine(catchment_config)

    # This is the key step to link the engine to the controller
    controller.set_diagnostic_engine(engine)

    # 3. Manually run the simulation loop to test the new architecture
    num_steps = sim_params.get('num_steps', 1)
    controller.results = {name: [] for name in controller.components} # Manual initialization

    print("\n--- Running Real-Twin Simulation with Feedback Loop ---")

    output_data = []

    for t in range(num_steps):
        # a. Prepare raw inputs for this time step
        current_inputs = {}
        for col in twin_rain_obs.columns:
            if col != 'time_step':
                current_inputs[col] = twin_rain_obs[col].iloc[t]
        for col in twin_flow_obs.columns:
             if col != 'time_step':
                current_inputs[col] = twin_flow_obs[col].iloc[t]

        # b. Run diagnostics for the current step
        engine.run_step(t, current_inputs, controller.results)

        # c. Perform data correction
        corrected_inputs = current_inputs.copy()
        if engine.sensor_health.get('RG2', 100) < 50:
            if 'RG2' in corrected_inputs and 'RG1' in corrected_inputs:
                print(f"  CORRECTION: Replacing RG2 value ({corrected_inputs['RG2']:.2f}) with RG1 value ({corrected_inputs['RG1']:.2f})")
                corrected_inputs['RG2'] = corrected_inputs['RG1']

        # d. Run one step of the simulation
        inflows_for_step = {name: {} for name in controller.components}
        for name in controller.components:
             if name == 'Catchment1': inflows_for_step[name]['rainfall'] = corrected_inputs.get('RG1', 0)
             if name == 'Catchment2': inflows_for_step[name]['rainfall'] = corrected_inputs.get('RG2', 0)
             if name == 'Catchment3': inflows_for_step[name]['rainfall'] = corrected_inputs.get('RG3', 0)

        for comp_name in controller.execution_order:
            controller._execute_component(comp_name, inflows_for_step)

        # e. Store results for this time step
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

    # Save final results to a CSV
    final_df = pd.DataFrame(output_data)
    final_output_path = 'examples/real_twin_framework/final_results.csv'
    final_df.to_csv(final_output_path, index=False)
    print(f"Final simulation results with diagnostics saved to {final_output_path}")

if __name__ == "__main__":
    main()
