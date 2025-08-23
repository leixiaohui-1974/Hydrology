import pandas as pd
from collections import deque

class DiagnosticEngine:
    """
    The 'brain' of the Real-Twin framework. It performs online diagnostics
    on the data being fed to the Digital Twin model.
    """
    def __init__(self, catchment_config):
        """
        Initializes the Diagnostic Engine.

        Args:
            catchment_config (dict): A dictionary describing the catchments,
                                     their areas, and their connections.
                                     Example:
                                     {
                                         'Catchment1': {'area_km2': 120, 'upstream': 'Catchment2', 'rain_gauge': 'RG1'},
                                         'Catchment2': {'area_km2': 200, 'upstream': 'Catchment3', 'rain_gauge': 'RG2'},
                                         'Catchment3': {'area_km2': 150, 'upstream': None, 'rain_gauge': 'RG3'}
                                     }
        """
        self.catchment_config = catchment_config
        self.history = {} # To store recent history for calculations
        for catchment_id in self.catchment_config:
            self.history[catchment_id] = {
                'rain': deque(maxlen=6), # Sliding window of 6 hours/steps
                'inflow': deque(maxlen=6),
                'outflow': deque(maxlen=6),
                'obs_flow': deque(maxlen=6)
            }

        # Health scores for rain gauges
        self.sensor_health = {v['rain_gauge']: 100 for k, v in catchment_config.items() if v['rain_gauge']}
        self.reliability_index = 100
        self.alert_penalty = 1.0

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
        self.reliability_index = s_h * self.alert_penalty
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
        # self._check_runoff_coefficient() # Disabling this check for now
        self._check_observation_consistency()
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

    def _check_runoff_coefficient(self):
        """
        Task 2.2: Perform online runoff coefficient cross-check.
        """
        print("Checking Runoff Coefficients...")
        for catchment_id, config in self.catchment_config.items():
            history = self.history[catchment_id]
            if len(history['rain']) < history['rain'].maxlen:
                print(f"  {catchment_id}: Not enough data yet.")
                continue

            # Calculate total rainfall and runoff over the window
            # Rainfall is in mm. Flow is in m3/s. Time step is 1 day (86400s).
            # Convert flow to runoff depth in mm.
            # Volume (m3) = Flow (m3/s) * 86400 (s/day)
            # Depth (m) = Volume (m3) / Area (m2)
            # Depth (mm) = Depth (m) * 1000

            area_m2 = config['area_km2'] * 1e6

            total_inflow_m3 = sum(history['inflow']) * 86400
            total_outflow_m3 = sum(history['outflow']) * 86400
            net_runoff_m3 = total_outflow_m3 - total_inflow_m3
            net_runoff_mm = (net_runoff_m3 / area_m2) * 1000

            total_rainfall_mm = sum(history['rain'])

            if total_rainfall_mm > 5: # Only calculate if there's meaningful rain
                runoff_coeff = net_runoff_mm / total_rainfall_mm
                print(f"  {catchment_id}: Runoff Coeff = {runoff_coeff:.2f}")

                # Task 2.3: Update Sensor Health Score
                rain_gauge = config['rain_gauge']
                if runoff_coeff < 0.1 or runoff_coeff > 1.0:
                    print(f"    ALERT: Unreasonable runoff coefficient for {catchment_id}!")
                    # This is a simple rule, a more sophisticated one would be needed.
                    # If coeff is too high, rain gauge might be under-reporting or flow is over-reporting.
                    # If coeff is too low, rain gauge might be over-reporting (or clogged).
                    self.sensor_health[rain_gauge] = max(0, self.sensor_health[rain_gauge] - 20)
                    print(f"    Health score for {rain_gauge} reduced to {self.sensor_health[rain_gauge]}")
                else:
                    # Healthy behavior, score recovers slowly
                    self.sensor_health[rain_gauge] = min(100, self.sensor_health[rain_gauge] + 5)
            elif net_runoff_mm > 5: # Significant runoff but no significant rain
                print(f"    ALERT: Significant runoff detected for {catchment_id} with no corresponding rainfall.")
                rain_gauge = config['rain_gauge']
                self.sensor_health[rain_gauge] = max(0, self.sensor_health[rain_gauge] - 25)
                print(f"    Health score for {rain_gauge} reduced to {self.sensor_health[rain_gauge]}")
            else:
                print(f"  {catchment_id}: Not enough rainfall to calculate coefficient.")

        print("Current Sensor Health:", self.sensor_health)
