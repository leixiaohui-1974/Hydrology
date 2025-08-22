import sys
import os
import numpy as np

# Adjust path to import from the root of the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '../..')))

from common.config_parser import ConfigParser

def run_and_verify():
    """
    Runs the flexible mapping example and verifies the results.
    """
    config_file = os.path.join(SCRIPT_DIR, 'config.yaml')

    print(f"--- Running Flexible Mapping Example from: {config_file} ---")

    parser = ConfigParser(config_file)
    _, _, global_inputs = parser.build_simulation()

    print("\n--- Verifying Global Inputs ---")

    expected_key = "my_model"
    expected_data = np.array([10, 20, 30])

    if expected_key in global_inputs:
        print(f"Key '{expected_key}' found in global_inputs. OK.")

        loaded_data = global_inputs[expected_key]
        if np.array_equal(loaded_data, expected_data):
            print(f"Data for '{expected_key}' is correct: {loaded_data}. OK.")
        else:
            print(f"ERROR: Data for '{expected_key}' is INCORRECT.")
            print(f"Expected: {expected_data}")
            print(f"Got: {loaded_data}")
    else:
        print(f"ERROR: Key '{expected_key}' NOT found in global_inputs.")
        print(f"Available keys: {list(global_inputs.keys())}")

if __name__ == "__main__":
    run_and_verify()
