"""
Calibrate Complex Watershed Model with EnKF
===========================================

This script runs a calibration simulation for the complex case study,
demonstrating the use of parameter zones with the Ensemble Kalman Filter (EnKF).
"""
import os
import sys
import numpy as np
import pandas as pd
import yaml
import copy

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.config_parser import ConfigParser
from hydro_model.enkf import EnsembleKalmanFilter

# --- Helper functions for state management ---

def get_model_states(controller):
    """Extracts all internal states from hydrological model components."""
    states = []
    for comp in controller.components.values():
        if hasattr(comp, 'runoff_module'):
            states.append(comp.runoff_module.S)
        if hasattr(comp, 'routing_module'):
            states.extend([comp.routing_module.I_prev, comp.routing_module.O_prev])
    return np.array(states)

def set_model_states(controller, state_vector):
    """Sets all internal states for hydrological model components."""
    i = 0
    for comp in controller.components.values():
        if hasattr(comp, 'runoff_module'):
            comp.runoff_module.S = state_vector[i]
            i += 1
        if hasattr(comp, 'routing_module'):
            comp.routing_module.I_prev = state_vector[i]
            comp.routing_module.O_prev = state_vector[i+1]
            i += 2

# --- The core model forward function for EnKF ---

def model_forward_factory(base_controller, params_to_calibrate, initial_component_params, n_model_states, obs_components_map, global_inputs, sim_params):
    """
    Factory to create the model_forward function with all necessary context.
    """
    num_steps = sim_params.get('num_steps', 1)
    dt = sim_params.get('dt_seconds', 3600)

    # Create a generator for the base controller to avoid re-creating it
    base_run_generator = base_controller.run(num_steps=1, dt=dt, global_inputs={k: [v[0]] for k, v in global_inputs.items()})

    def model_forward(augmented_state_vector, t):
        """
        Runs the simulation for one time step for a single ensemble member.
        """
        # 1. Create a deepcopy of the controller to avoid side effects between ensemble members
        member_controller = copy.deepcopy(base_controller)

        # 2. Unpack state vector and set states/parameters for the member
        model_states = augmented_state_vector[:n_model_states]
        calib_params = augmented_state_vector[n_model_states:]
        set_model_states(member_controller, model_states)

        # 3. Apply parameter corrections based on the state vector
        for i, param_info in enumerate(params_to_calibrate):
            zone_id = param_info['zone']
            param_name = param_info['param_name']
            module_name, p_name = param_name.split('.')

            # Use a multiplicative correction factor for physical realism
            initial_guess = param_info['initial_guess']
            if initial_guess == 0: initial_guess = 1e-6 # Avoid division by zero
            correction_factor = calib_params[i] / initial_guess

            zone = member_controller.parameter_zones[zone_id]
            for comp_idx, component in enumerate(zone.components):
                initial_val = initial_component_params[i][comp_idx]
                module = getattr(component, module_name)
                # Ensure corrected params are non-negative
                setattr(module, p_name, max(0, initial_val * correction_factor))

        # 4. Run the model for one time step
        # Create a generator for this specific member
        member_global_inputs = {k: [v[t]] for k, v in global_inputs.items()}
        run_generator = member_controller.run(num_steps=1, dt=dt, global_inputs=member_global_inputs)
        next(run_generator) # Advance one step

        # 5. Get the new state and the predicted observation
        new_model_states = get_model_states(member_controller)

        # Add small noise to parameters for inflation (helps prevent filter divergence)
        param_noise = np.random.normal(0, 0.01, len(calib_params))
        new_calib_params = calib_params + param_noise

        new_augmented_state = np.concatenate([new_model_states, new_calib_params])

        # Get predicted observations from the specified components
        predicted_obs = []
        for zone_id in sorted(obs_components_map.keys()): # Sort to ensure consistent order
             obs_comp_name = obs_components_map[zone_id]
             predicted_obs.append(member_controller.components[obs_comp_name].get_outflow())

        return new_augmented_state, np.array(predicted_obs)

    return model_forward

def main():
    print("--- 1. Loading Simulation Configuration ---")
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    parser = ConfigParser(config_path)
    controller, sim_params, global_inputs = parser.build_simulation()

    print(f"Simulation loaded. Found {len(controller.components)} components.")
    print(f"Found {len(controller.parameter_zones)} parameter zones: {list(controller.parameter_zones.keys())}")

    # --- 2. Load Calibration Settings & Data ---
    print("\n--- 2. Loading Calibration Settings & Data ---")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    calib_config = config.get("calibration_settings", {})
    enkf_config = calib_config.get("enkf", {})
    params_to_calibrate = enkf_config.get("parameters_to_calibrate", [])

    observed_data = {}
    obs_components = {}
    sorted_zone_ids = sorted(controller.parameter_zones.keys())

    for zone_id in sorted_zone_ids:
        zone_config = next((item for item in config['parameter_zones'] if item["zone_id"] == zone_id), None)
        obs_comp_name = zone_config.get('observation_component')
        obs_components[zone_id] = obs_comp_name
        obs_info = calib_config.get("observed_data", {}).get(zone_id, {})
        obs_path = os.path.join(os.path.dirname(__file__), obs_info['file'])
        df = pd.read_csv(obs_path, index_col=0)
        observed_data[zone_id] = df.iloc[:, 0].values
        print(f"Loaded observed data for '{zone_id}' at component '{obs_comp_name}'")

    num_steps = sim_params.get('num_steps')
    true_observations = np.array([observed_data[z_id] for z_id in sorted_zone_ids]).T

    # --- 3. Initialize EnKF ---
    print("\n--- 3. Initializing Ensemble Kalman Filter ---")
    n_ensemble = enkf_config.get("n_ensemble", 50)
    enkf = EnsembleKalmanFilter(n_ensemble=n_ensemble)

    # --- 4. Define Augmented State Vector & Create Initial Ensemble ---
    print("\n--- 4. Creating Initial Ensemble ---")
    initial_model_states = get_model_states(controller)
    n_model_states = len(initial_model_states)
    initial_param_values = [p['initial_guess'] for p in params_to_calibrate]
    initial_param_uncertainty = [p['initial_uncertainty'] for p in params_to_calibrate]
    n_params = len(initial_param_values)
    initial_augmented_state = np.concatenate([initial_model_states, initial_param_values])
    state_uncertainty = np.abs(initial_model_states) * 0.1 + 1.0
    augmented_uncertainty = np.concatenate([state_uncertainty, initial_param_uncertainty])

    ensemble = np.random.normal(loc=initial_augmented_state, scale=augmented_uncertainty, size=(n_ensemble, len(initial_augmented_state))).T
    ensemble[n_model_states:, :] = np.maximum(0, ensemble[n_model_states:, :])
    enkf.initialize(initial_states=ensemble)
    print(f"EnKF initialized with ensemble shape: {enkf.states.shape}")

    # --- 5. Run Assimilation Loop ---
    print("\n--- 5. Starting Data Assimilation Loop ---")

    # Store initial parameter values for each component in each zone
    initial_component_params = {}
    for i, param_info in enumerate(params_to_calibrate):
        zone = controller.parameter_zones[param_info['zone']]
        module_name, p_name = param_info['param_name'].split('.')
        initial_component_params[i] = [getattr(getattr(c, module_name), p_name) for c in zone.components]

    # Create the model_forward function
    model_forward = model_forward_factory(controller, params_to_calibrate, initial_component_params, n_model_states, obs_components, global_inputs, sim_params)

    # Set up storage for results
    state_history = np.zeros((num_steps, len(initial_augmented_state)))
    simulated_flows = np.zeros((num_steps, len(obs_components)))

    R = np.diag([enkf_config.get("observation_error_variance")] * len(obs_components))

    for t in range(num_steps):
        print(f"  - Step {t+1}/{num_steps}")
        forecast_obs = enkf.forecast(model_forward=model_forward, t=t)
        enkf.analysis(observation=true_observations[t, :], forecast_observations=forecast_obs, R=R)

        mean_state = enkf.states.mean(axis=1)
        state_history[t, :] = mean_state
        _, mean_flow = model_forward(mean_state, t=t)
        simulated_flows[t, :] = mean_flow

    print("\n--- 6. Saving Results ---")

    # Save parameter evolution
    param_names = [f"{p['zone']}_{p['param_name']}" for p in params_to_calibrate]
    params_df = pd.DataFrame(state_history[:, n_model_states:], columns=param_names, index=pd.to_datetime(np.arange(num_steps), unit='h'))
    params_df.to_csv('results/complex_calibration_parameters.csv')
    print("Parameter evolution saved to results/complex_calibration_parameters.csv")

    # Save flow results
    flow_results_df = pd.DataFrame(simulated_flows, columns=[f"sim_{z}" for z in sorted_zone_ids])
    for i, z_id in enumerate(sorted_zone_ids):
        flow_results_df[f"obs_{z_id}"] = true_observations[:num_steps, i]
    flow_results_df.to_csv('results/complex_calibration_flows.csv')
    print("Flow results saved to results/complex_calibration_flows.csv")

    print("\n--- 7. Plotting Results ---")
    os.system("python examples/complex_case_study/plot_results.py")

    print("\n--- Calibration and plotting complete ---")

if __name__ == "__main__":
    main()
