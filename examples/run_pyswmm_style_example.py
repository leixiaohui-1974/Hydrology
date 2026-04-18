"""
Example: Using the PySWMM-like Interface
=========================================

This script demonstrates how to use the new `pyswmm`-like wrapper to
run a simulation, access data, and control a hydraulic structure at runtime.
"""
import sys
import os

# Add the project root to the Python path
# This is necessary to import the pyswmm_wrapper from an example script.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from pyswmm_wrapper.simulation import Simulation

def main():
    """Main execution function."""
    # The config file now contains a controllable Gate.
    config_file = "examples/hydraulic_features_example/config.yaml"
    print(f"--- Running PySWMM-style example with config: {config_file} ---")

    # Use the with statement to manage the simulation context
    with Simulation(config_file) as sim:
        # Get the link object that contains our gate
        # In this config, the HydraulicModel component is named "MyRiver"
        river_link = sim.links["MyRiver"]

        print("\n--- Starting simulation loop ---")
        print("Time\t\t\tFlow (m3/s)\tGate Opening (m)")
        print("-" * 50)

        # Iterate through the simulation step-by-step
        for step in sim:
            # Access results from the current time step
            current_flow = river_link.flow
            current_gate_opening = river_link.target_setting

            # Print current state
            print(f"{sim.current_time}\t{current_flow:.2f}\t\t{current_gate_opening:.2f}")

            # --- Runtime Control Logic ---
            # If the flow is high, close the gate partially.
            # If the flow is low, open it back up.
            if current_flow > 20.0:
                if current_gate_opening != 0.5:
                    print("  -> High flow detected! Closing gate.")
                    river_link.target_setting = 0.5
            else:
                if current_gate_opening != 1.0:
                    print("  -> Flow is normal. Opening gate.")
                    river_link.target_setting = 1.0

    print("\n--- Simulation finished ---")


if __name__ == "__main__":
    main()
