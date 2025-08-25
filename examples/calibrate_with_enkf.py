import numpy as np
import pandas as pd
import sys
import os
# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SimpleRunoffModule
from hydro_model.routing import SimpleRouting
from hydro_model.enkf import EnsembleKalmanFilter

def model_forward_augmented(state_vector, rainfall, pet, area_km2):
    """
    A wrapper that works with an augmented state vector and the new modular model.

    :param state_vector: A numpy array [S, Q_s, S_max, k_q, k_s, c_loss]
    ...
    :return: A tuple of (new_state_vector, simulated_flow_m3s)
    """
    # 1. Unpack states and parameters
    S, Q_s, S_max, k_q, k_s, c_loss = state_vector

    # Ensure parameters are physically plausible
    params = {
        'S_max': max(1, S_max),
        'k_q': max(0.01, min(1.0, k_q)),
        'k_s': max(0.01, min(1.0, k_s)),
        'c_loss': max(0, c_loss)
    }

    # 2. Create and configure model instances for one step
    runoff_module = SimpleRunoffModule(**params)
    runoff_module.S = S  # Set current state

    routing_module = SimpleRouting(**params)
    routing_module.Q_s = Q_s # Set current state

    # The HydrologicalModel is now just a container for the logic
    model = HydrologicalModel(name="enkf_model", runoff_module=runoff_module, routing_module=routing_module)

    runoff_mm = model.run(rainfall, pet)

    # 3. Convert runoff to flow (m3/s)
    simulated_flow_m3s = (runoff_mm / 1000) * (area_km2 * 1e6) / (24 * 3600)

    # 4. Return the new state vector and the simulated flow
    # Add a small random noise to parameters for inflation
    param_noise = np.random.normal(0, [0.1, 0.001, 0.001, 0.0001])
    new_params = np.array([params['S_max'], params['k_q'], params['k_s'], params['c_loss']]) + param_noise

    new_state_vector = np.array([runoff_module.S, routing_module.Q_s, *new_params])

    return new_state_vector, simulated_flow_m3s

def run_open_loop(model_params, rainfall_data, pet_data, area_km2):
    """Runs a standard simulation with the new modular structure."""
    runoff_module = SimpleRunoffModule(**model_params)
    routing_module = SimpleRouting(**model_params)
    model = HydrologicalModel(name="open_loop_model", runoff_module=runoff_module, routing_module=routing_module)

    results = []
    for rain, pet in zip(rainfall_data, pet_data):
        runoff_mm = model.run(rain, pet)
        flow_m3s = (runoff_mm / 1000) * (area_km2 * 1e6) / (24 * 3600)
        results.append(flow_m3s)
    return np.array(results)


if __name__ == "__main__":
    # --- 1. Setup and Load Data ---
    rainfall_df = pd.read_csv('data/rainfall.csv', index_col='date', parse_dates=True)
    pet_df = pd.read_csv('data/pet.csv', index_col='date', parse_dates=True)
    observed_flow_df = pd.read_csv('data/observed_flow.csv', index_col='date', parse_dates=True)

    catchment_area = 150 + 200 + 120 # km^2
    rainfall = rainfall_df['rainfall_1'].values
    pet = pet_df['pet'].values
    observed_flow = observed_flow_df['flow_m3s'].values

    # --- 2. Initialize EnKF ---
    N_ENSEMBLE = 50
    R = 10**2

    enkf = EnsembleKalmanFilter(n_ensemble=N_ENSEMBLE)

    # --- 3. Create Initial Ensemble ---
    initial_guess = {
        'S': 10.0, 'Q_s': 5.0,
        'S_max': 180.0, 'k_q': 0.7, 'k_s': 0.15, 'c_loss': 0.06
    }
    initial_uncertainty = {
        'S': 5.0, 'Q_s': 2.0,
        'S_max': 50.0, 'k_q': 0.2, 'k_s': 0.1, 'c_loss': 0.02
    }

    ensemble = np.random.normal(
        loc=list(initial_guess.values()),
        scale=list(initial_uncertainty.values()),
        size=(N_ENSEMBLE, len(initial_guess))
    ).T

    enkf.initialize(initial_states=ensemble)

    # --- 4. Run Assimilation Loop ---
    T = len(rainfall)
    assimilated_flows = np.zeros(T)
    state_history = np.zeros((T, len(initial_guess)))

    print("Running Ensemble Kalman Filter assimilation...")
    for t in range(T):
        forecast_obs = enkf.forecast(
            model_forward=model_forward_augmented,
            rainfall=rainfall[t],
            pet=pet[t],
            area_km2=catchment_area
        )

        enkf.analysis(
            observation=observed_flow[t],
            forecast_observations=forecast_obs,
            R=R
        )

        mean_state = enkf.states.mean(axis=1)
        state_history[t, :] = mean_state

        _, mean_flow = model_forward_augmented(mean_state, rainfall[t], pet[t], catchment_area)
        assimilated_flows[t] = mean_flow

    print("Assimilation complete.")

    # --- 5. Run Open-Loop for Comparison ---
    print("Running open-loop simulation for comparison...")
    open_loop_params = {k: v for k, v in initial_guess.items() if k not in ['S', 'Q_s']}
    open_loop_flows = run_open_loop(open_loop_params, rainfall, pet, catchment_area)

    # --- 6. Save Results ---
    results_df = pd.DataFrame({
        'observed_flow': observed_flow,
        'open_loop_flow': open_loop_flows,
        'assimilated_flow': assimilated_flows
    }, index=observed_flow_df.index)

    param_names = ['S', 'Q_s', 'S_max', 'k_q', 'k_s', 'c_loss']
    params_df = pd.DataFrame(state_history, columns=param_names, index=observed_flow_df.index)

    output_flow_path = 'results/enkf_flow_results.csv'
    output_params_path = 'results/enkf_parameter_evolution.csv'
    os.makedirs(os.path.dirname(output_flow_path), exist_ok=True)

    results_df.to_csv(output_flow_path)
    params_df.to_csv(output_params_path)

    print(f"Results saved to '{output_flow_path}' and '{output_params_path}'")
