import sys
import os
import pandas as pd

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from real_twin.diagnostic_engine import DiagnosticEngine

def main():
    """
    Main execution function for running the Online Diagnostic Engine.
    """
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


    print("--- Initializing Diagnostic Run ---")

    # 1. Load all necessary data
    twin_sim_results = pd.read_csv('twin_results.csv', index_col='time_step')
    twin_rain_obs = pd.read_csv('twin_rainfall.csv', index_col='time_step')
    twin_flow_obs = pd.read_csv('twin_flow.csv', index_col='time_step')
    catchment_def = pd.read_csv('../../data/catchment_definition.csv')

    # 2. Prepare configuration for the engine
    catchment_config = {
        'Catchment1': {'area_km2': 120, 'upstream': 'Catchment2', 'rain_gauge': 'RG1', 'flow_gauge': 'FG1'},
        'Catchment2': {'area_km2': 200, 'upstream': 'Catchment3', 'rain_gauge': 'RG2', 'flow_gauge': 'FG2'},
        'Catchment3': {'area_km2': 150, 'upstream': None, 'rain_gauge': 'RG3', 'flow_gauge': None}
    }

    # 3. Initialize and run the engine
    engine = DiagnosticEngine(catchment_config)
    num_steps = len(twin_sim_results)

    for t in range(num_steps):
        engine.run_step(t, twin_sim_results, twin_rain_obs, twin_flow_obs)

    print("\n--- Diagnostic Run Finished ---")

if __name__ == "__main__":
    main()
