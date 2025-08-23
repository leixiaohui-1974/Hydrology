import pandas as pd
import numpy as np
from sensors import RainGauge, FlowGauge

def main():
    """
    This script generates the observation data for the Digital Twin model
    by sampling from the ground truth with a virtual sensor network.
    """
    print("--- Starting Data Pipeline for Digital Twin ---")

    # 1. Generate Synthetic Ground Truth Data
    # Instead of running a model, we create a synthetic "truth" to have full control.
    # We'll create a simple hydrograph shape.
    num_steps = 30
    time_steps = range(num_steps)
    peak_flow = 50
    base_flow = 5
    # A simple triangular hydrograph for the most upstream catchment
    q3_truth = np.concatenate([
        np.linspace(base_flow, peak_flow, num_steps // 2),
        np.linspace(peak_flow, base_flow, num_steps - num_steps // 2)
    ])
    # Lag and attenuate for downstream catchments
    q2_truth = np.roll(q3_truth, 1) * 0.9 + base_flow
    q1_truth = np.roll(q2_truth, 1) * 0.9 + base_flow

    ground_truth_flow = pd.DataFrame({
        'Catchment3': q3_truth,
        'Catchment2': q2_truth,
        'Catchment1': q1_truth
    }, index=time_steps)

    # The "true" rainfall is assumed to be proportional to the runoff (flow rate)
    ground_truth_rain = ground_truth_flow.copy()
    ground_truth_rain.columns = ['rainfall_3', 'rainfall_2', 'rainfall_1']

    # 2. Define Sensor Network
    sensors = [
        RainGauge('RG1', 'rainfall_1', error_std_dev=0.5),
        RainGauge('RG2', 'rainfall_2', error_std_dev=0.5),
        RainGauge('RG3', 'rainfall_3', error_std_dev=0.5),
        FlowGauge('FG1', 'Catchment1', error_std_dev=1.0),
        FlowGauge('FG2', 'Catchment2', error_std_dev=1.0),
    ]

    # 3. Introduce Fault Scenarios
    faulty_sensor_name = 'RG2'
    fault_start_step = 15
    missed_storm_start = 10
    missed_storm_end = 12

    # 4. Generate Twin Observations
    twin_observations = []

    for t in range(len(ground_truth_flow)):
        current_obs = {'time_step': t}

        # Sample from each sensor
        for sensor in sensors:
            if isinstance(sensor, RainGauge):
                true_value = ground_truth_rain[sensor.location_id].iloc[t]
                # --- Apply Faults ---
                # Scenario 1: Clogging
                if sensor.name == faulty_sensor_name and t >= fault_start_step:
                    sensor.set_fault_state(True, 'clogging')
                else:
                    sensor.set_fault_state(False)

                observed_rain = sensor.sample(true_value)

                # Scenario 2: Missed Storm
                if missed_storm_start <= t <= missed_storm_end:
                    observed_rain = 1.0 # All gauges report low rain

                current_obs[sensor.name] = observed_rain

            elif isinstance(sensor, FlowGauge):
                true_value = ground_truth_flow[sensor.location_id].iloc[t]
                observed_flow = sensor.sample(true_value)

                # Scenario 2: Missed Storm (manual override of flow)
                if missed_storm_start <= t <= missed_storm_end:
                    observed_flow = 30.0 # But flow gauges show high flow

                current_obs[sensor.name] = observed_flow

        twin_observations.append(current_obs)

    # 5. "Cheat" to create ideal twin simulation results for diagnostics
    # We want a scenario where the runoff coefficient is normally stable,
    # so we can clearly see the impact of the faulty sensor.

    catchment_def = pd.read_csv('data/catchment_definition.csv')
    twin_results = pd.DataFrame(index=ground_truth_flow.index)
    target_runoff_coeff = 0.5

    # Calculate runoff based on a fixed runoff coefficient from the *observed* twin rain
    twin_rain_df = pd.DataFrame(twin_observations).set_index('time_step')[['RG1', 'RG2', 'RG3']]

    # Catchment 3 (most upstream)
    area_c3 = catchment_def[catchment_def['pfaf_code'] == 3]['area_km2'].iloc[0] * 1e6
    rain_c3_mm = twin_rain_df['RG3']
    rain_c3_m3 = (rain_c3_mm / 1000) * area_c3
    runoff_c3_m3 = rain_c3_m3 * target_runoff_coeff
    twin_results['Catchment3'] = runoff_c3_m3 / 86400 # convert back to m3/s

    # Catchment 2
    area_c2 = catchment_def[catchment_def['pfaf_code'] == 2]['area_km2'].iloc[0] * 1e6
    rain_c2_mm = twin_rain_df['RG2']
    rain_c2_m3 = (rain_c2_mm / 1000) * area_c2
    local_runoff_c2_m3s = (rain_c2_m3 * target_runoff_coeff) / 86400
    twin_results['Catchment2'] = twin_results['Catchment3'] + local_runoff_c2_m3s # Add upstream flow

    # Catchment 1 (outlet)
    area_c1 = catchment_def[catchment_def['pfaf_code'] == 1]['area_km2'].iloc[0] * 1e6
    rain_c1_mm = twin_rain_df['RG1']
    rain_c1_m3 = (rain_c1_mm / 1000) * area_c1
    local_runoff_c1_m3s = (rain_c1_m3 * target_runoff_coeff) / 86400
    twin_results['Catchment1'] = twin_results['Catchment2'] + local_runoff_c1_m3s

    # 6. Save all data
    twin_flow_df = pd.DataFrame(twin_observations).set_index('time_step')[['FG1', 'FG2']]

    twin_rain_path = 'examples/real_twin_framework/twin_rainfall.csv'
    twin_flow_path = 'examples/real_twin_framework/twin_flow.csv'
    twin_results_path = 'examples/real_twin_framework/twin_results.csv'

    twin_rain_df.to_csv(twin_rain_path)
    twin_flow_df.to_csv(twin_flow_path)
    twin_results.to_csv(twin_results_path)

    print(f"Twin rainfall data saved to {twin_rain_path}")
    print(f"Twin flow data saved to {twin_flow_path}")
    print("--- Data Pipeline Finished ---")

if __name__ == '__main__':
    main()
