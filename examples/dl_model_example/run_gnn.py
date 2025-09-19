import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.config_parser import ConfigParser

def main():
    """
    Main execution function.
    """


    config_file = os.path.join(os.path.dirname(__file__), 'config_gnn.yaml')

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
    dt = sim_params.get('dt_seconds', 86400)
    num_steps = sim_params.get('num_steps', 1)

    # Run the simulation
    print("\n--- Running Simulation ---")
    controller.run(
        num_steps=num_steps,
        dt=dt,
        global_inputs=global_inputs
    )

    print("\n--- Final State of All Components ---")
    for name, component in controller.components.items():
        outflow = component.get_outflow()
        print(f"Component: '{name}', Final Outflow: {outflow:.3f}")

if __name__ == "__main__":
    main()
