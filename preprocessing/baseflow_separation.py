import pandas as pd
import numpy as np

def lyne_hollick_filter(flow_series: pd.Series, alpha: float = 0.925, passes: int = 3, n_reflect: int = 30):
    """
    Separates baseflow from a streamflow time series using the Lyne-Hollick digital filter.

    This implementation follows the standard three-pass method to avoid phase shifts.

    Args:
        flow_series (pd.Series): Time series of streamflow. Must have a regular frequency.
        alpha (float, optional): The filter parameter. Defaults to 0.925, a common value for daily data.
        passes (int, optional): The number of passes. Must be an odd number >= 1. Defaults to 3.
        n_reflect (int, optional): The number of data points to reflect at the start and end
                                   of the series to mitigate end effects. Defaults to 30.

    Returns:
        pd.DataFrame: A DataFrame with the original flow, the separated baseflow, and the quick flow.
    """
    if passes % 2 == 0 or passes < 1:
        raise ValueError("The number of passes must be an odd integer greater than or equal to 1.")

    # Convert Series to numpy array for performance
    flow = flow_series.to_numpy()

    if n_reflect >= len(flow):
        raise ValueError("n_reflect must be smaller than the length of the flow series.")

    # --- 1. Reflection ---
    # Reflect the start and end of the series to reduce end effects
    start_pad = np.flip(flow[:n_reflect])
    end_pad = np.flip(flow[-n_reflect:])
    reflected_flow = np.concatenate([start_pad, flow, end_pad])

    # --- 2. Filtering Passes ---
    quick_flow = np.zeros_like(reflected_flow)

    # First pass (forward)
    for i in range(1, len(reflected_flow)):
        term1 = alpha * quick_flow[i-1]
        term2 = ((1 + alpha) / 2) * (reflected_flow[i] - reflected_flow[i-1])
        quick_flow[i] = term1 + term2

    # Enforce constraints
    quick_flow = np.maximum(0, np.minimum(quick_flow, reflected_flow))
    base_flow = reflected_flow - quick_flow

    # Subsequent passes are run on the baseflow from the previous pass
    for _ in range(1, passes):
        if _ % 2 != 0: # Backward pass
            # The "quick flow" of the baseflow is the new adjustment
            adjustment = np.zeros_like(base_flow)
            for i in range(len(base_flow) - 2, -1, -1):
                term1 = alpha * adjustment[i+1]
                term2 = ((1 + alpha) / 2) * (base_flow[i] - base_flow[i+1])
                adjustment[i] = term1 + term2

            adjustment = np.maximum(0, np.minimum(adjustment, base_flow))
            base_flow = base_flow - adjustment

        else: # Forward pass
            adjustment = np.zeros_like(base_flow)
            for i in range(1, len(base_flow)):
                term1 = alpha * adjustment[i-1]
                term2 = ((1 + alpha) / 2) * (base_flow[i] - base_flow[i-1])
                adjustment[i] = term1 + term2

            adjustment = np.maximum(0, np.minimum(adjustment, base_flow))
            base_flow = base_flow - adjustment

    # --- 3. Finalization ---
    # Trim the reflected ends from the final baseflow series
    final_baseflow = base_flow[n_reflect:-n_reflect]

    # Create a DataFrame to return the results
    result = pd.DataFrame({
        'total_flow': flow_series,
        'baseflow': final_baseflow,
        'quick_flow': flow_series - final_baseflow
    }, index=flow_series.index)

    return result
