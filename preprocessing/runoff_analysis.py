import pandas as pd
import numpy as np

def calculate_runoff_coefficient(rainfall_series: pd.Series, flow_series: pd.Series, catchment_area_km2: float):
    """
    Calculates the runoff coefficient for a given period from rainfall and flow data.

    Args:
        rainfall_series (pd.Series): Time series of areal average rainfall (in mm).
                                     Index must be a DatetimeIndex.
        flow_series (pd.Series): Time series of observed streamflow (in m^3/s).
                                 Index must be a DatetimeIndex.
        catchment_area_km2 (float): The area of the catchment in square kilometers.

    Returns:
        float: The calculated runoff coefficient, or None if calculation is not possible.
    """
    if not isinstance(rainfall_series.index, pd.DatetimeIndex) or not isinstance(flow_series.index, pd.DatetimeIndex):
        raise ValueError("Input Series must have a DatetimeIndex.")

    # --- 1. Align Data ---
    # Combine data into a single DataFrame and drop rows with missing values
    df = pd.DataFrame({'rainfall_mm': rainfall_series, 'flow_m3s': flow_series}).dropna()

    if df.empty:
        print("Warning: No overlapping data between rainfall and flow series. Cannot calculate runoff coefficient.")
        return None

    # --- 2. Calculate Volumes ---
    # Get the time step in seconds by calculating the difference between the first two timestamps
    if len(df.index) < 2:
        raise ValueError("Cannot determine time step frequency with less than two data points.")
    time_delta = df.index[1] - df.index[0]
    time_delta_seconds = time_delta.total_seconds()

    # Total rainfall volume in cubic meters
    # Rainfall (mm) -> Rainfall (m) by dividing by 1000
    # Area (km^2) -> Area (m^2) by multiplying by 1,000,000
    # Volume = Depth (m) * Area (m^2)
    total_rainfall_volume = (df['rainfall_mm'] / 1000) * (catchment_area_km2 * 1e6)
    total_rainfall_volume_sum = total_rainfall_volume.sum()

    # Total runoff volume in cubic meters
    # Volume = Flow Rate (m^3/s) * Time Step (s)
    total_runoff_volume = df['flow_m3s'] * time_delta_seconds
    total_runoff_volume_sum = total_runoff_volume.sum()

    if total_rainfall_volume_sum == 0:
        print("Warning: Total rainfall volume is zero. Cannot calculate runoff coefficient.")
        return None

    # --- 3. Calculate Coefficient ---
    runoff_coefficient = total_runoff_volume_sum / total_rainfall_volume_sum

    # --- 4. Validate and Return ---
    print(f"Total Rainfall Volume: {total_rainfall_volume_sum:,.2f} m^3")
    print(f"Total Runoff Volume: {total_runoff_volume_sum:,.2f} m^3")
    print(f"Calculated Runoff Coefficient: {runoff_coefficient:.4f}")

    if not (0.0 <= runoff_coefficient <= 1.0):
        print(f"Warning: Calculated runoff coefficient ({runoff_coefficient:.4f}) is outside the plausible range of [0, 1].")
        print("Please check the consistency and units of your rainfall, flow, and catchment area data.")

    return runoff_coefficient
