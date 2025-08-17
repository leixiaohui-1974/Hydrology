import numpy as np
import pandas as pd
from hydro_model.model import SimpleConceptualModel
from hydro_model.enkf import EnsembleKalmanFilter

# This is the core function that integrates the hydrological model with the EnKF's state vector
def model_forward_augmented(state_vector, rainfall, pet, area_km2):
    """
    A wrapper for the hydrological model that works with an augmented state vector.

    :param state_vector: A numpy array [S, Q_s, S_max, k_q, k_s, c_loss]
    :param rainfall: Rainfall for the current time step (mm)
    :param pet: PET for the current time step (mm)
    :param area_km2: Catchment area for runoff conversion
    :return: A tuple of (new_state_vector, simulated_flow_m3s)
    """
    # 1. Unpack states and parameters
    S, Q_s, S_max, k_q, k_s, c_loss = state_vector

    # Ensure parameters are physically plausible (e.g., non-negative)
    S_max = max(1, S_max)
    k_q = max(0.01, min(1.0, k_q))
    k_s = max(0.01, min(1.0, k_s))
    c_loss = max(0, c_loss)

    params = {'S_max': S_max, 'k_q': k_q, 'k_s': k_s, 'c_loss': c_loss}

    # 2. Create and run the model for one step
    model = SimpleConceptualModel(params)
    model.S = S
    model.Q_s = Q_s

    runoff_mm = model.run(rainfall, pet)

    # 3. Convert runoff to flow (m3/s) to compare with observation
    simulated_flow_m3s = (runoff_mm / 1000) * (area_km2 * 1e6) / (24 * 3600)

    # 4. Return the new state vector and the simulated flow
    # Add a small random noise to parameters to prevent filter divergence (inflation)
    param_noise = np.random.normal(0, [0.1, 0.001, 0.001, 0.0001])
    new_params = np.array([S_max, k_q, k_s, c_loss]) + param_noise

    new_state_vector = np.array([model.S, model.Q_s, *new_params])

    return new_state_vector, simulated_flow_m3s

def run_open_loop(model_params, rainfall_data, pet_data, area_km2):
    """Runs a standard simulation without data assimilation."""
    model = SimpleConceptualModel(model_params)
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

    # For this example, we use data for a single basin (sub-basin 1 from previous example)
    # The area is the sum of all sub-basins in the first example
    catchment_area = 150 + 200 + 120 # km^2
    rainfall = rainfall_df['rainfall_1'].values
    pet = pet_df['pet'].values
    observed_flow = observed_flow_df['flow_m3s'].values

    # --- 2. Initialize EnKF ---
    N_ENSEMBLE = 50
    # Observation error variance (m3/s)^2. This is a key tuning parameter.
    R = 10**2

    enkf = EnsembleKalmanFilter(n_ensemble=N_ENSEMBLE)

    # --- 3. Create Initial Ensemble ---
    # Initial guesses for states and parameters
    initial_guess = {
        'S': 10.0, 'Q_s': 5.0,
        'S_max': 180.0, 'k_q': 0.7, 'k_s': 0.15, 'c_loss': 0.06
    }
    # Uncertainty of initial guesses (standard deviation)
    initial_uncertainty = {
        'S': 5.0, 'Q_s': 2.0,
        'S_max': 50.0, 'k_q': 0.2, 'k_s': 0.1, 'c_loss': 0.02
    }

    # Create the ensemble by drawing from normal distributions
    ensemble = np.random.normal(
        loc=list(initial_guess.values()),
        scale=list(initial_uncertainty.values()),
        size=(N_ENSEMBLE, len(initial_guess))
    ).T # Transpose to get (n_states, n_ensemble)

    enkf.initialize(initial_states=ensemble)

    # --- 4. Run Assimilation Loop ---
    T = len(rainfall)
    assimilated_flows = np.zeros(T)
    state_history = np.zeros((T, len(initial_guess)))

    print("Running Ensemble Kalman Filter assimilation...")
    for t in range(T):
        # Forecast step
        forecast_obs = enkf.forecast(
            model_forward=model_forward_augmented,
            rainfall=rainfall[t],
            pet=pet[t],
            area_km2=catchment_area
        )

        # Analysis step
        enkf.analysis(
            observation=observed_flow[t],
            forecast_observations=forecast_obs,
            R=R
        )

        # Store results (the mean of the ensemble)
        mean_state = enkf.states.mean(axis=1)
        state_history[t, :] = mean_state

        # We need to re-calculate the flow based on the updated mean state for plotting
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

    results_df.to_csv('results/enkf_flow_results.csv')
    params_df.to_csv('results/enkf_parameter_evolution.csv')

    print("Results saved to 'results/enkf_flow_results.csv' and 'results/enkf_parameter_evolution.csv'")
