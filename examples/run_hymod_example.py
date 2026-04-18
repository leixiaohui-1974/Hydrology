"""
Example: Running a Hydrological Model with the HYMOD Runoff Module
====================================================================

This script demonstrates how to load and run a hydrological model that uses the
new HymodRunoffModule, defined entirely in a YAML file.
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


import sys
from common.config_parser import ConfigParser

def main():
    """
    Main execution function.
    """
    config_file = "examples/config_hymod.yaml"
    print(f"--- Loading configuration from: {config_file} ---")

    try:
        parser = ConfigParser(config_file)
        controller, sim_params, global_inputs = parser.build_simulation()
    except Exception as e:
        print(f"Error building simulation from config file: {e}")
        sys.exit(1)

    print(f"--- Simulation built successfully ---")
    components = [c.name for c in controller.components.values()]
    print(f"Components: {components}")

    # Get simulation parameters
    dt = sim_params.get('dt_seconds', 86400)
    num_steps = sim_params.get('num_steps', 1)

    # Run the simulation
    final_status = {}
    for status in controller.run(
        num_steps=num_steps,
        dt=dt,
        global_inputs=global_inputs
    ):
        final_status = status
        print(f"Step {status['step']}/{status['num_steps']}, Final Outflow: {status['final_outflow']:.3f}")


    print("\n--- Simulation Finished ---")
    if components and final_status:
        final_component_name = components[-1]
        final_outflow = final_status.get('final_outflow', 0)
        print(f"Final state of component '{final_component_name}': Outflow = {final_outflow:.3f}")
    else:
        print("Could not determine final state.")


if __name__ == "__main__":
    main()
