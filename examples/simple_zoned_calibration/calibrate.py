"""
Simple Zoned Calibration Example using EnKF
===========================================

This script demonstrates a simplified sequential, upstream-to-downstream
calibration using the Ensemble Kalman Filter (EnKF).
"""

import os
import sys
import numpy as np
import pandas as pd
import yaml
import copy

# Add the project root to the Python path to allow imports from other directories
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.config_parser import ConfigParser
from hydro_model.enkf import EnsembleKalmanFilter

# --- Core Model Forward Function for EnKF ---

def model_forward_factory(base_controller, params_to_calibrate, global_inputs, sim_params):
    """
    Factory to create the model_forward function with the necessary context.
    This version is simplified to only handle parameters, not model states.
    """
    num_steps = sim_params.get('num_steps')
    dt = sim_params.get('dt_seconds')

    def model_forward(param_vector, t):
        """
        Runs the model for one time step for a single ensemble member.
        """
        member_controller = copy.deepcopy(base_controller)

        # Apply parameters from the vector to the model components in the correct zone
        for i, param_info in enumerate(params_to_calibrate):
            zone_id = param_info['zone']
            param_name = param_info['param_name']
            module_name, p_name = param_name.split('.')

            zone = member_controller.parameter_zones[zone_id]
            for component in zone.components:
                module = getattr(component, module_name)
                setattr(module, p_name, max(0, param_vector[i]))

        # Run the model for one time step
        member_global_inputs = {k: [v[t]] for k, v in global_inputs.items()}
        run_generator = member_controller.run(num_steps=1, dt=dt, global_inputs=member_global_inputs)
        next(run_generator)

        # Get the predicted observation for the specific component being observed
        # This is a simplified approach where we assume the calibration script knows
        # which component's outflow corresponds to the observation.
        zone_to_calibrate = params_to_calibrate[0]['zone']
        obs_comp_name = base_controller.parameter_zones[zone_to_calibrate].observation_component
        predicted_obs = member_controller.components[obs_comp_name].get_outflow()

        new_param_vector = param_vector
        return new_param_vector, np.array([predicted_obs])

    return model_forward

def main():
    print("--- 1. Loading Simulation Configuration ---")
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    parser = ConfigParser(config_path)
    base_controller, sim_params, global_inputs = parser.build_simulation()

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    calib_config = config.get("calibration_settings", {})
    enkf_config = calib_config.get("enkf", {})
    all_params_to_calibrate = enkf_config.get("parameters_to_calibrate", [])
    num_steps = sim_params.get('num_steps')

    # --- 2. Prepare for Sequential Calibration ---
    sorted_zone_ids = sorted(base_controller.parameter_zones.keys())
    print(f"\n--- Starting Sequential Calibration for zones: {sorted_zone_ids} ---")

    for zone_id in sorted_zone_ids:
        print(f"\n--- Calibrating Zone: {zone_id} ---")

        params_for_this_zone = [p for p in all_params_to_calibrate if p['zone'] == zone_id]
        if not params_for_this_zone:
            print(f"No parameters to calibrate in '{zone_id}'. Skipping.")
            continue

        print(f"Calibrating parameters: {[p['param_name'] for p in params_for_this_zone]}")

        # Load observation data for this zone
        obs_info = calib_config.get("observed_data", {}).get(zone_id, {})
        obs_path = os.path.join(os.path.dirname(__file__), obs_info['file'])
        true_observation_data = pd.read_csv(obs_path, index_col=0).iloc[:, 0].values

        # Initialize EnKF
        n_ensemble = enkf_config.get("n_ensemble", 50)
        enkf = EnsembleKalmanFilter(n_ensemble=n_ensemble)

        initial_param_values = [p['initial_guess'] for p in params_for_this_zone]
        initial_param_uncertainty = [p['initial_uncertainty'] for p in params_for_this_zone]

        ensemble = np.random.normal(loc=initial_param_values, scale=initial_param_uncertainty, size=(n_ensemble, len(initial_param_values))).T
        enkf.initialize(initial_states=ensemble)

        # Run Assimilation Loop
        # The model_forward function is now simpler and specific to the zone being calibrated
        model_forward = model_forward_factory(base_controller, params_for_this_zone, global_inputs, sim_params)

        R = np.diag([enkf_config.get("observation_error_variance")])

        for t in range(num_steps):
            # The forecast step now correctly calls model_forward without extra args
            forecast_observations = enkf.forecast(model_forward=model_forward, t=t)
            # The analysis step uses the forecast observations directly
            enkf.analysis(observation=true_observation_data[t], forecast_observations=forecast_observations, R=R)

        # Persist Calibrated Parameters
        final_params_for_zone = enkf.states.mean(axis=1)
        print(f"Finished calibration for '{zone_id}'.")
        for i, param_info in enumerate(params_for_this_zone):
            param_name = param_info['param_name']
            calibrated_value = final_params_for_zone[i]
            print(f"  - Calibrated {param_name}: {calibrated_value:.2f}")

            # Update the parameters in the base controller
            zone = base_controller.parameter_zones[zone_id]
            # Add observation component to parameter zone object to make it accessible here
            zone.observation_component = next((item for item in config['parameter_zones'] if item["zone_id"] == zone_id), None).get('observation_component')
            module_name, p_name = param_name.split('.')
            for component in zone.components:
                setattr(getattr(component, module_name), p_name, max(0, calibrated_value))

    print("\n--- Sequential Calibration Complete ---")

if __name__ == "__main__":
    main()
