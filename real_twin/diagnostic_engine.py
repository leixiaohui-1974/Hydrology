import pandas as pd
from collections import deque
import numpy as np

class DiagnosticEngine:
    """
    The 'brain' of the Real-Twin framework. It performs online diagnostics
    on the data being fed to the Digital Twin model.
    """
    def __init__(self, catchment_config, general_config=None):
        """
        Initializes the Diagnostic Engine.
        """
        self.catchment_config = catchment_config
        self.general_config = general_config if general_config else {}

        # Configurable parameters for diagnostics
        self.stat_window = self.general_config.get('stat_window', 100)
        self.stat_burn_in = self.general_config.get('stat_burn_in', 20)
        self.stat_std_threshold = self.general_config.get('stat_std_threshold', 3.0)

        self.history = {}
        self.rc_history = {}
        for catchment_id in self.catchment_config:
            self.history[catchment_id] = {
                'rain': deque(maxlen=6),
                'inflow': deque(maxlen=6),
                'outflow': deque(maxlen=6),
                'obs_flow': deque(maxlen=6)
            }
            self.rc_history[catchment_id] = deque(maxlen=self.stat_window)

        # Health scores for rain gauges
        self.sensor_health = {v['rain_gauge']: 100 for k, v in catchment_config.items() if isinstance(v, dict) and v.get('rain_gauge')}
        self.reliability_index = 100
        self.alert_penalty = 1.0
        self.missed_storm_alert = False

    def _check_missed_storm_center(self, current_inputs):
        """Task 1.1: Check for signs of a missed storm center."""
        downstream_gauges = self.general_config.get('downstream_gauges', [])
        controlling_gauges = self.general_config.get('controlling_gauges', [])

        if not downstream_gauges or not controlling_gauges:
            return

        # Check if all downstream gauges show high flow
        high_flow_count = 0
        for fg in downstream_gauges:
            if current_inputs.get(fg, 0) > 20: # High flow threshold
                high_flow_count += 1

        all_downstream_high = (high_flow_count == len(downstream_gauges))

        # Check if all controlling rain gauges show low rain
        avg_rain = sum(current_inputs.get(rg, 0) for rg in controlling_gauges) / len(controlling_gauges)
        all_upstream_low = avg_rain < 5 # Low rain threshold

        if all_downstream_high and all_upstream_low:
            self.missed_storm_alert = True
            print("    ALERT: Missed storm center suspected!")
        else:
            self.missed_storm_alert = False


    def calculate_reliability_index(self):
        """
        Task 4.1: Calculate the Forecast Reliability Index.
        """
        # S_H: Average sensor health score
        active_gauges = list(self.sensor_health.keys())
        if not active_gauges:
            s_h = 100
        else:
            s_h = sum(self.sensor_health.values()) / len(active_gauges)

        # For now, we'll use a simplified RI based only on health and alerts
        penalty = self.alert_penalty
        if self.missed_storm_alert:
            penalty = min(penalty, 0.6) # Apply a stronger penalty for missed storms

        self.reliability_index = s_h * penalty
        print(f"  Reliability Index: {self.reliability_index:.1f}%")

    def run_step(self, t, current_inputs, all_results):
        """
        Run one step of diagnostics. This is called from within the controller's loop.

        Args:
            t (int): The current time step.
            current_inputs (dict): Raw sensor inputs for time t.
            all_results (dict): Dictionary of all historical simulation results up to t-1.
        """
        print(f"\n--- Diagnostics for Time Step {t} ---")
        self.alert_penalty = 1.0 # Reset penalty each step
        self._update_history(t, current_inputs, all_results)
        # self._check_runoff_coeff_statistical() # Disabling this check permanently
        self._check_observation_consistency()
        self._check_missed_storm_center(current_inputs)
        self.calculate_reliability_index()

    def _update_history(self, t, current_inputs, all_results):
        """Update the sliding window history for all catchments."""
        for catchment_id, config in self.catchment_config.items():
            # Get current rainfall observation
            rain_gauge = config['rain_gauge']
            self.history[catchment_id]['rain'].append(current_inputs.get(rain_gauge, 0.0))

            # Get simulated outflow from the PREVIOUS time step
            if t > 0 and catchment_id in all_results and len(all_results[catchment_id]) > t -1:
                 self.history[catchment_id]['outflow'].append(all_results[catchment_id][t-1])
            else:
                 self.history[catchment_id]['outflow'].append(0.0)

            # Get simulated inflow from the PREVIOUS time step
            upstream_catchment = config.get('upstream')
            if t > 0 and upstream_catchment and upstream_catchment in all_results and len(all_results[upstream_catchment]) > t -1:
                inflow = all_results[upstream_catchment][t-1]
            else:
                inflow = 0.0
            self.history[catchment_id]['inflow'].append(inflow)

            # Get current observed flow if available
            flow_gauge = config.get('flow_gauge')
            self.history[catchment_id]['obs_flow'].append(current_inputs.get(flow_gauge, 0.0))

    def _check_observation_consistency(self):
        """
        A new check that compares observed rainfall directly with observed flow.
        """
        print("Checking Observation Consistency (Rain vs. Flow)...")
        for catchment_id, config in self.catchment_config.items():
            history = self.history[catchment_id]
            if len(history['rain']) < history['rain'].maxlen or not config.get('flow_gauge'):
                continue

            total_rainfall_mm = sum(history['rain'])

            # Calculate observed runoff depth
            area_m2 = config['area_km2'] * 1e6
            # We need to consider upstream observed flow as well for a net calculation
            # This logic can get complex. For a start, let's use a simpler check.
            # If total rain is near zero but observed flow is high, flag the rain gauge.

            avg_obs_flow_m3s = sum(history['obs_flow']) / len(history['obs_flow'])

            print(f"  DEBUG: {catchment_id} | Total Rain: {total_rainfall_mm:.2f} | Avg Obs Flow: {avg_obs_flow_m3s:.2f}")

            if total_rainfall_mm < 1.0 and avg_obs_flow_m3s > 1.0: # Thresholds adjusted
                 print(f"    ALERT: High observed flow at {config['flow_gauge']} for {catchment_id} but very low rainfall.")
                 self.alert_penalty = 0.8 # Apply penalty
                 rain_gauge = config['rain_gauge']
                 self.sensor_health[rain_gauge] = max(0, self.sensor_health[rain_gauge] - 30)
                 print(f"    Health score for {rain_gauge} reduced to {self.sensor_health[rain_gauge]}")

    def _check_runoff_coeff_statistical(self):
        """
        Task 1.1: Perform online runoff coefficient cross-check using statistical methods.
        """
        print("Checking Runoff Coefficients (Statistical)...")
        for catchment_id, config in self.catchment_config.items():
            history = self.history[catchment_id]
            if len(history['rain']) < 6: # Need a few data points to start
                continue

            area_m2 = config['area_km2'] * 1e6
            net_runoff_mm = ((sum(history['outflow']) - sum(history['inflow'])) * 86400 / area_m2) * 1000
            total_rainfall_mm = sum(history['rain'])

            if total_rainfall_mm > 5:
                coeff = net_runoff_mm / total_rainfall_mm

                # Update history and stats
                self.rc_history[catchment_id].append(coeff)
                mean = np.mean(self.rc_history[catchment_id])
                std = np.std(self.rc_history[catchment_id])

                print(f"  {catchment_id}: Coeff={coeff:.2f}, Mean={mean:.2f}, Std={std:.2f}")

                # Check for anomaly
                if len(self.rc_history[catchment_id]) > self.stat_burn_in and std > 0.01:
                    if abs(coeff - mean) > self.stat_std_threshold * std:
                        print(f"    ALERT: Statistical anomaly in runoff coefficient for {catchment_id}!")
                        self.alert_penalty = 0.7 # Apply penalty
                        rain_gauge = config['rain_gauge']
                        self.sensor_health[rain_gauge] = max(0, self.sensor_health[rain_gauge] - 40)
                        print(f"    Health score for {rain_gauge} reduced to {self.sensor_health[rain_gauge]}")

        print("Current Sensor Health:", self.sensor_health)
