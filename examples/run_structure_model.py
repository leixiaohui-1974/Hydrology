"""
Example: Running a Hydraulic Model with a Structure
===================================================

This script demonstrates how to run a hydraulic model that includes a
structure (a gate) within the river reach.
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


import numpy as np

# --- Import Model Components ---
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.structures import Gate

def main():
    print("--- 1. Setting up hydraulic model with a gate ---")

    # --- Hydraulic Component: A River Reach with a Gate ---
    num_nodes = 21
    reach_geom = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(num_nodes)],
        lengths=np.full(num_nodes - 1, 250.0), # 5km total length
        slope=0.001,
        manning_n=0.03
    )

    # Define a gate structure at node 10 (the middle of the reach)
    gate = Gate(name="mid_reach_gate", node_index=10, opening_height=0.5, width=10)
    print(f"Defined a gate structure: '{gate.name}' at node {gate.node_index}")

    # Downstream water level is fixed
    downstream_level = 2.0 # meters

    river = HydraulicModel(
        name="R1_regulated_river",
        reach=reach_geom,
        dt=10.0,
        downstream_level=downstream_level,
        structures=[gate] # Pass the list of structures here
    )

    # Set initial conditions for the river
    river.Q[:] = 15.0 # Constant flow
    # Set water level to be flat initially
    for i in range(num_nodes):
        river.Z[i] = river.Z_bed[i] + 2.5

    print(f"Created hydraulic component: '{river.name}'")


    # --- 2. Define Simulation Inputs ---
    num_steps = 100

    # For this test, we will use a constant inflow and downstream level
    inflow_hydrograph = np.full(num_steps, 15.0)
    downstream_hydrograph = np.full(num_steps, downstream_level)

    # --- 3. Run the Simulation (using the standalone runner) ---
    river.run(
        num_steps=num_steps,
        Q_inflow_hydrograph=inflow_hydrograph,
        Z_downstream_hydrograph=downstream_hydrograph
    )

    # --- 4. Inspect Final State ---
    print("\n--- 4. Final Model State ---")
    print("The simplified gate logic should force Z[9] and Z[10] to be equal.")
    print("\nFinal state of river reach:")
    print("Node | Water Elev (m) | Discharge (m^3/s)")
    print("---- | -------------- | -----------------")
    for i in range(river.num_nodes):
        print(f"{i:4d} | {river.Z[i]:14.3f} | {river.Q[i]:17.3f}")

if __name__ == "__main__":
    main()
