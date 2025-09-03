import sys
import os
import pandas as pd

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.config_parser import ConfigParser

def main():
    """
    Main execution function for running the Ground Truth simulation.
    """


    config_file = 'config_ground_truth.yaml'

    print(f"--- Loading Ground Truth configuration from: {config_file} ---")
    try:
        parser = ConfigParser(config_file)
        controller, sim_params, global_inputs = parser.build_simulation()
    except Exception as e:
        print(f"Error building simulation from config file: {e}")
        sys.exit(1)

    print(f"--- Ground Truth Simulation built successfully ---")

    # Run the simulation
    print("\n--- Running Ground Truth Simulation ---")
    # The run method is a generator, so we need to iterate through it to execute
    for _ in controller.run(
        num_steps=sim_params.get('num_steps', 1),
        dt=sim_params.get('dt_seconds', 86400),
        global_inputs=global_inputs
    ):
        pass # The results are being stored in controller.results

    print("\n--- Ground Truth Simulation Finished ---")

    # Save the results to a CSV file
    results_df = pd.DataFrame(controller.results)
    output_path = 'ground_truth_results.csv'
    results_df.to_csv(output_path, index_label='time_step')

    print(f"Ground truth results saved to {output_path}")

if __name__ == "__main__":
    main()
