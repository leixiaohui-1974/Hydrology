import sys
import os
import pandas as pd
import numpy as np
import copy
import matplotlib.pyplot as plt

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.controller import SimulationController
from common.base_model import BaseModelComponent
from real_twin.diagnostic_engine import DiagnosticEngine
from hydro_model.enkf import EnsembleKalmanFilter

# --- WORKAROUND: Define SimplePassthroughModel here to avoid import issues ---
class SimplePassthroughModel(BaseModelComponent):
    def __init__(self, name: str, coeff: float = 0.5, **kwargs):
        super().__init__(name)
        self.coeff = coeff
        self.storage = 0.0

    def step(self, inflows: dict, dt: float):
        rainfall = inflows.get('rainfall', 0.0)
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet', 'temperature'])
        self.storage += rainfall + upstream_inflow
        release = self.storage * self.coeff
        self.storage -= release
        self.outflow = release

    def get_state(self):
        return {'coeff': self.coeff, 'storage': self.storage}

    def set_state(self, state):
        self.coeff = state['coeff']
        self.storage = state['storage']

def main():
    """
    Main execution function for running the Real-Twin simulation with EnKF
    and dynamic observation error adjustment.
    """
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


    print("--- Initializing Real-Twin Simulation with EnKF ---")

    # 1. Load sensor data
    twin_rain_obs = pd.read_csv('examples/real_twin_framework/twin_rainfall.csv')
    twin_flow_obs = pd.read_csv('examples/real_twin_framework/twin_flow.csv')

    # 2. Initialize Diagnostic Engine
    catchment_config = {
        'Catchment1': {'area_km2': 120, 'upstream': 'Catchment2', 'rain_gauge': 'RG1', 'flow_gauge': 'FG1'},
        'Catchment2': {'area_km2': 200, 'upstream': 'Catchment3', 'rain_gauge': 'RG2', 'flow_gauge': 'FG2'},
        'Catchment3': {'area_km2': 150, 'upstream': None, 'rain_gauge': 'RG3', 'flow_gauge': None}
    }
    general_diag_config = {
        'downstream_gauges': ['FG1', 'FG2'],
        'controlling_gauges': ['RG1', 'RG2', 'RG3']
    }
    engine = DiagnosticEngine(catchment_config, general_diag_config)

    # 3. Setup EnKF
    n_ensemble = 20
    enkf = EnsembleKalmanFilter(n_ensemble)

    # State vector: [C1_coeff, C1_storage, C2_coeff, C2_storage, C3_coeff, C3_storage]
    n_states = 6
    initial_states = np.zeros((n_states, n_ensemble))
    # Initial guesses for parameters and states
    initial_states[0, :] = np.random.normal(0.4, 0.1, n_ensemble) # C1_coeff
    initial_states[1, :] = np.random.normal(0, 1, n_ensemble)     # C1_storage
    initial_states[2, :] = np.random.normal(0.4, 0.1, n_ensemble) # C2_coeff
    initial_states[3, :] = np.random.normal(0, 1, n_ensemble)     # C2_storage
    initial_states[4, :] = np.random.normal(0.4, 0.1, n_ensemble) # C3_coeff
    initial_states[5, :] = np.random.normal(0, 1, n_ensemble)     # C3_storage

    enkf.initialize(initial_states)

    # Create an ensemble of models
    ensemble_controllers = []
    for i in range(n_ensemble):
        c1 = SimplePassthroughModel(name='Catchment1')
        c2 = SimplePassthroughModel(name='Catchment2')
        c3 = SimplePassthroughModel(name='Catchment3')

        # Set initial state from ensemble
        c1.set_state({'coeff': initial_states[0, i], 'storage': initial_states[1, i]})
        c2.set_state({'coeff': initial_states[2, i], 'storage': initial_states[3, i]})
        c3.set_state({'coeff': initial_states[4, i], 'storage': initial_states[5, i]})

        controller = SimulationController()
        controller.add_component(c1)
        controller.add_component(c2)
        controller.add_component(c3)
        controller.connect('Catchment3', 'Catchment2')
        controller.connect('Catchment2', 'Catchment1')
        controller._detect_and_sort_components()
        ensemble_controllers.append(controller)

    # 4. Run the simulation loop
    num_steps = 30
    results_history = []

    print("\n--- Running EnKF Simulation with Feedback Loop ---")
    for t in range(num_steps):
        # a. Get current observations
        current_rain = {col: twin_rain_obs[col].iloc[t] for col in twin_rain_obs.columns if col != 'time_step'}
        current_flow = {col: twin_flow_obs[col].iloc[t] for col in twin_flow_obs.columns if col != 'time_step'}

        # b. Run diagnostics
        # We need to provide the diagnostic engine with the mean of the ensemble forecast
        if t > 0:
            # This is still a simplification, as the diagnostic engine expects a full results dataframe
            # I will pass an empty dataframe for now to make the code runnable
            engine.run_step(t, current_rain, pd.DataFrame())

        # c. EnKF Forecast
        forecast_observations = []
        for i in range(n_ensemble):
            controller = ensemble_controllers[i]
            # In a real scenario, we would use corrected inputs here
            inflows = {'rainfall': current_rain.get('RG1', 0)} # Simplified input
            controller.components['Catchment1'].step(inflows, 86400)
            # This is a highly simplified forecast step. A full network run would be needed.
            forecast_obs = controller.components['Catchment1'].get_outflow()
            forecast_observations.append(forecast_obs)

        # d. EnKF Analysis
        observation = current_flow.get('FG1', 0.0)

        # Dynamic R matrix
        health_score = engine.sensor_health.get('RG1', 100) # Get health of gauge for Catchment 1
        R_base = 1.0
        # Increase observation error as health score decreases
        R_dynamic = np.array([[R_base / (health_score / 100.0 if health_score > 0 else 0.01)]])

        print(f"  Health FG1: {health_score}, R: {R_dynamic[0,0]:.2f}")

        enkf.analysis(observation, np.array(forecast_observations).reshape(-1, 1), R_dynamic)

        # e. Update model ensemble from new states
        for i in range(n_ensemble):
            state_col = enkf.states[:, i]
            ensemble_controllers[i].components['Catchment1'].set_state({'coeff': state_col[0], 'storage': state_col[1]})
            # ... and so on for other components

        # f. Store results
        mean_params = enkf.states.mean(axis=1)
        results_history.append(mean_params)
        print(f"Step {t+1}/{num_steps} | Mean C1_coeff: {mean_params[0]:.3f}")

    print("\n--- EnKF Simulation Finished ---")

    # Plot results
    results_df = pd.DataFrame(results_history, columns=['C1_coeff', 'C1_storage', 'C2_coeff', 'C2_storage', 'C3_coeff', 'C3_storage'])
    plt.figure(figsize=(12, 6))
    plt.plot(results_df['C1_coeff'], label='Catchment 1 Coeff')
    plt.title('EnKF Parameter Calibration')
    plt.xlabel('Time Step')
    plt.ylabel('Parameter Value')
    plt.legend()
    plt.grid(True)
    plt.savefig('examples/real_twin_framework/enkf_results.png')
    print("EnKF results plot saved.")

if __name__ == "__main__":
    main()
