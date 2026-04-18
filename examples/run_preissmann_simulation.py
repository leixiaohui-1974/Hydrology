"""
Run Preissmann Model Simulation
===============================

This script sets up and runs a test case for the 1D hydraulic model.
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


import numpy as np
from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.reach import RiverReach
from preissmann_model.model import HydraulicModel

def calculate_normal_depth(Q, width, slope, n):
    """
    Calculates normal depth for a rectangular channel using Manning's equation.
    Uses a simple iterative solver.
    """
    y = 1.0  # Initial guess
    for _ in range(20): # 20 iterations should be enough
        if y <= 0: return 0.0
        A = width * y
        P = width + 2 * y
        Rh = A / P
        if Rh < 1e-6: return y
        Q_calc = (A * Rh**(2/3) * slope**0.5) / n
        if abs(Q_calc) < 1e-6: return y
        y = y * (Q / Q_calc)**0.5
    return y

def main():
    """
    Main function to set up and run the simulation.
    """
    print("--- 1. Setting up hydraulic model simulation ---")

    # --- Channel Geometry ---
    num_nodes = 21
    reach_length = 2000.0  # meters
    width = 20.0          # meters
    slope = 0.001         # m/m
    manning_n = 0.03

    dx = reach_length / (num_nodes - 1)
    cross_sections = [RectangularCrossSection(width=width) for _ in range(num_nodes)]
    lengths = np.full(num_nodes - 1, dx)

    reach = RiverReach(cross_sections, lengths, slope, manning_n)

    # --- Simulation Parameters ---
    dt = 5.0  # seconds
    num_steps = 360 # Simulate for 30 minutes (360 * 5s = 1800s)

    # --- Initial Conditions ---
    Q_initial = 50.0  # m^3/s

    print(f"Calculating normal depth for initial flow Q={Q_initial} m^3/s...")
    y_normal = calculate_normal_depth(Q_initial, width, slope, manning_n)
    print(f"Normal depth y_n = {y_normal:.2f} m")

    # --- Boundary Conditions ---
    # Upstream: Small flood wave
    Q_inflow = np.full(num_steps, Q_initial)
    Q_inflow[10:70] = Q_initial + 50 * np.sin(np.pi * (np.arange(60) / 60.0))

    # Downstream: Fixed water level at normal depth
    Z_downstream_val = y_normal # Bed elevation at downstream end is 0
    Z_downstream = np.full(num_steps, Z_downstream_val)

    # --- Instantiate and Initialize Model ---
    model = HydraulicModel(
        name='TestReach',
        reach=reach,
        dt=dt,
        downstream_level=Z_downstream_val
    )

    # Set initial Q for all nodes
    model.Q[:] = Q_initial

    # Set initial Z based on normal depth, following the bed slope
    # model.Z_bed is calculated in __init__
    for i in range(num_nodes):
        model.Z[i] = model.Z_bed[i] + y_normal

    print("\n--- 2. Initial State ---")
    print(f"Initial Q: {model.Q[0]:.2f} m^3/s")
    print(f"Initial Z (upstream): {model.Z[0]:.2f} m")
    print(f"Initial Z (downstream): {model.Z[-1]:.2f} m")

    # --- 3. Run the Simulation ---
    print("\n--- 3. Running simulation ---")
    model.run(num_steps, Q_inflow, Z_downstream)

    # --- 4. Print Results ---
    print("\n--- 4. Final State ---")
    print("Node | Bed Elev (m) | Water Elev (m) | Depth (m) | Discharge (m^3/s)")
    print("---- | ------------ | -------------- | --------- | -----------------")
    for i in range(num_nodes):
        depth = model.Z[i] - model.Z_bed[i]
        print(f"{i:4d} | {model.Z_bed[i]:12.2f} | {model.Z[i]:14.2f} | {depth:9.2f} | {model.Q[i]:17.2f}")


if __name__ == "__main__":
    main()
