"""
Example: Running a Hydraulic Model with a Pump from a YAML Configuration
=========================================================================

This script demonstrates how to load and run a hydraulic model that includes a
pump structure, where the entire simulation is defined in a YAML file.
"""
import sys
from common.config_parser import ConfigParser

def main():
    """
    Main execution function.
    """
    # The configuration file is hardcoded for this example
    config_file = "examples/config_pump.yaml"
    print(f"--- Loading configuration from: {config_file} ---")

    try:
        parser = ConfigParser(config_file)
        controller, sim_params, global_inputs = parser.build_simulation()
    except Exception as e:
        print(f"Error building simulation from config file: {e}")
        sys.exit(1)

    print(f"--- Simulation built successfully ---")
    print(f"Components: {[c.name for c in controller.components.values()]}")

    # Get simulation parameters
    dt = sim_params.get('dt_seconds', 60)
    num_steps = sim_params.get('num_steps', 1)

    # Run the simulation
    # The controller.run() is a generator, so we need to iterate through it
    for status in controller.run(
        num_steps=num_steps,
        dt=dt,
        global_inputs=global_inputs
    ):
        # You could add real-time plotting or logging here
        pass

    print("\n--- Simulation Finished ---")

    # --- Inspect Final State ---
    # Get the hydraulic model component to inspect its state
    river_model = controller.components.get("R1_pumped_reach")
    if river_model:
        print("\n--- Final Model State for 'R1_pumped_reach' ---")
        print("The pump at node 5 should lift water from Z[4] to Z[5].")
        print(f"Final Q at pump location (node 5) is {river_model.Q[5]:.2f} m^3/s.")
        print("\nFinal state of river reach:")
        print("Node | Water Elev (m) | Discharge (m^3/s)")
        print("---- | -------------- | -----------------")
        for i in range(river_model.num_nodes):
            print(f"{i:4d} | {river_model.Z[i]:14.3f} | {river_model.Q[i]:17.3f}")
    else:
        print("Could not find component 'R1_pumped_reach' to inspect results.")


if __name__ == "__main__":
    main()
