"""
Runner for the Ultimate Case Study
==================================

This script loads and runs the complex, 50+ component case study that includes
a mix of hydrological models and a looped hydraulic network.
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.config_parser import ConfigParser

def main():
    """
    Main execution function.
    """
    config_file = "examples/ultimate_case_study/config.yaml"
    print(f"--- Loading Ultimate Case Study from: {config_file} ---")

    try:
        parser = ConfigParser(config_file)
        controller, sim_params, global_inputs = parser.build_simulation()
    except Exception as e:
        print(f"Error building simulation from config file: {e}")
        sys.exit(1)

    print(f"--- Simulation built successfully with {len(controller.components)} components. ---")

    # Get simulation parameters
    dt = sim_params.get('dt_seconds', 3600)
    num_steps = sim_params.get('num_steps', 1)

    # Run the simulation
    print("\n--- Running Ultimate Case Study Simulation ---")
    final_status = {}
    for status in controller.run(
        num_steps=num_steps,
        dt=dt,
        global_inputs=global_inputs
    ):
        final_status = status
        # Printing every step would be too verbose for this large simulation,
        # so we'll just print a progress marker periodically.
        if status['step'] % 50 == 0:
            print(f"  ... Step {status['step']}/{status['num_steps']} ...")

    print("\n--- Simulation Finished ---")
    final_outflow = final_status.get('final_outflow', 'N/A')
    print(f"Final Outflow: {final_outflow:.3f}")


if __name__ == "__main__":
    main()
