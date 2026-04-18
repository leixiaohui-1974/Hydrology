import sys
import os
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.config_parser import ConfigParser
from real_twin.diagnostic_engine import DiagnosticEngine

def main():
    """
    Main execution function for running the full Real-Twin simulation
    with a deeply integrated online diagnostic engine and feedback loop.
    """
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


    print("--- Initializing Real-Twin Simulation ---")

    # 1. Load configuration and raw sensor data
    config_file = 'config_ground_truth.yaml'
    twin_rain_obs = pd.read_csv('twin_rainfall.csv')
    twin_flow_obs = pd.read_csv('twin_flow.csv')

    # 2. Initialize Controller and Diagnostic Engine
    parser = ConfigParser(config_file)
    # Use the twin data for this simulation run
    parser.data_registry['rainfall_data'] = twin_rain_obs

    controller, sim_params, global_inputs = parser.build_simulation()

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

    controller.set_diagnostic_engine(engine)

    # Add flow observations to the global inputs for the diagnostic engine
    for col in twin_flow_obs.columns:
        if col != 'time_step':
            global_inputs[col] = twin_flow_obs[col].to_numpy()

    # 3. Run the simulation
    print("\n--- Running Real-Twin Simulation with Integrated Feedback Loop ---")
    for status in controller.run(
        num_steps=sim_params.get('num_steps', 30),
        dt=sim_params.get('dt_seconds', 86400),
        global_inputs=global_inputs
    ):
        print(f"Step {status['step']}/{status['num_steps']} | Reliability: {controller.diagnostic_engine.reliability_index:.1f}%")

    print("\n--- Real-Twin Simulation Finished ---")

    # 4. Save final results
    sim_results_df = pd.DataFrame(controller.results)
    diag_results_df = pd.DataFrame(controller.diagnostic_engine.results_history)
    final_df = pd.concat([sim_results_df, diag_results_df], axis=1)

    # Add raw and corrected data for comparison
    final_df['raw_RG2'] = twin_rain_obs['RG2'].values
    corrected_rg2 = final_df['raw_RG2'].copy()
    faulty_indices = final_df[final_df['health_RG2'] < 50].index
    # This is a simplification, we are re-calculating the correction after the fact for plotting
    # A full implementation would log the corrected values during the run.
    # For now, this is sufficient to demonstrate the effect.
    if not faulty_indices.empty:
        corrected_rg2[faulty_indices] = twin_rain_obs['RG1'][faulty_indices].values
    final_df['corrected_RG2'] = corrected_rg2

    final_output_path = 'final_results.csv'
    final_df.to_csv(final_output_path, index_label='time_step')
    print(f"Final simulation results with diagnostics saved to {final_output_path}")

if __name__ == "__main__":
    main()
