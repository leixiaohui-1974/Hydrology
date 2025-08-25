"""
Example: Running a Hydraulic Model with a Pump
===============================================

This script demonstrates how to run a hydraulic model that includes a
pump structure to lift water between two locations.
"""
import numpy as np

# --- Import Model Components ---
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.structures import Pump

def main():
    print("--- 1. Setting up hydraulic model with a pump ---")

    # --- Hydraulic Component: A flat channel with a pump ---
    num_nodes = 11
    reach_geom = RiverReach(
        cross_sections=[RectangularCrossSection(width=5) for _ in range(num_nodes)],
        lengths=np.full(num_nodes - 1, 100.0),
        slope=0.0, # Flat channel
        manning_n=0.02
    )

    # Define a pump at node 5 (the middle of the reach)
    # The curve is H = 5 - 0.05*Q^2  (a=-0.05, b=0, c=5)
    # This means it provides 5m of lift at Q=0, and less as Q increases.
    pump = Pump(name="main_pump", node_index=5, curve_coeffs=(-0.05, 0, 5.0))
    print(f"Defined a pump structure: '{pump.name}' at node {pump.node_index}")

    # The downstream water level is fixed at a level higher than upstream.
    upstream_level = 2.0
    downstream_level = 6.0 # 4m higher than upstream

    river = HydraulicModel(
        name="R1_pumped_reach",
        reach=reach_geom,
        dt=10.0,
        downstream_level=downstream_level,
        structures=[pump]
    )

    # Set initial conditions: still water at the upstream level
    river.Q[:] = 0.0
    river.Z[:] = upstream_level
    print(f"Created hydraulic component: '{river.name}'")

    # --- 2. Define Simulation Inputs ---
    num_steps = 100

    # We use fixed water levels at both ends for this test.
    # The pump will induce the flow.
    inflow_hydrograph = np.full(num_steps, upstream_level)
    downstream_hydrograph = np.full(num_steps, downstream_level)

    # --- 3. Run the Simulation ---
    # We need a custom run loop here since the main `run` method assumes Q inflow.
    print(f"--- Running simulation for component '{river.name}' ---")
    for i in range(num_steps):
        # We provide a 'Z_inflow' key instead of 'Q_inflow'
        inflows = {'Z_inflow': inflow_hydrograph[i]}
        river.downstream_level = downstream_hydrograph[i]
        river.step(inflows, river.dt)
    print("--- Simulation finished ---")


    # --- 4. Inspect Final State ---
    print("\n--- 4. Final Model State ---")
    print("The pump at node 5 should lift water from Z[4] to Z[5].")
    print(f"Expected head lift at Q~0 is ~5m. Final Q is {river.Q[5]:.2f} m^3/s.")
    print("\nFinal state of river reach:")
    print("Node | Water Elev (m) | Discharge (m^3/s)")
    print("---- | -------------- | -----------------")
    for i in range(river.num_nodes):
        print(f"{i:4d} | {river.Z[i]:14.3f} | {river.Q[i]:17.3f}")

if __name__ == "__main__":
    main()
