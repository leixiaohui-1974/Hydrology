"""
Example: Using the PySWMM-like Interface with a Hydrological Model
===================================================================

This script demonstrates how to use the `pyswmm`-like wrapper to
run a hydrological model, access its parameters, and modify them at
runtime.
"""
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from pyswmm_wrapper.simulation import Simulation

def main():
    """Main execution function."""
    config_file = "examples/config_hymod.yaml"
    print(f"--- Running PySWMM-style HYMOD example with config: {config_file} ---")

    # Use the with statement to manage the simulation context
    with Simulation(config_file) as sim:
        # Get the subcatchment object.
        # In the config_hymod.yaml, the component is named "MyHymodCatchment".
        catchment = sim.subcatchments["MyHymodCatchment"]

        print("\n--- Starting simulation loop ---")
        print("Time\t\t\tRunoff (m3/s)\tCMAX (mm)")
        print("-" * 50)

        # Iterate through the simulation step-by-step
        for step in sim:
            # Access results and parameters from the current time step
            current_runoff = catchment.runoff
            current_cmax = catchment.cmax

            # Print current state
            print(f"{sim.current_time}\t{current_runoff:.3f}\t\t{current_cmax:.2f}")

            # --- Runtime Control Logic ---
            # Let's change the CMAX parameter after a few steps to see its effect.
            if sim._current_step == 5:
                # Let's check the initial value before changing it
                initial_cmax = catchment.cmax
                print(f"  -> Step 5 reached. Initial CMAX is {initial_cmax:.2f}.")
                print("  -> Doubling CMAX to simulate change in soil storage.")
                catchment.cmax = initial_cmax * 2

    print("\n--- Simulation finished ---")


if __name__ == "__main__":
    main()
