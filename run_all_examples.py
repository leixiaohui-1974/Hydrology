import os
import sys
import time
import importlib.util
import traceback
from utils.performance_monitor import PerformanceMonitor

def get_all_example_scripts(root_dir='examples'):
    """Finds all Python scripts in the examples directory."""
    scripts = []
    # Exclude scripts that are known to be problematic or not meant to be run standalone
    exclude_list = [
        'run_hymod_example.py', # Requires user input
        'run_xaj_example.py', # Requires user input
        'run_scs_example.py', # Requires user input
        'dissolve_subbasins.py', # Helper script
        'inspect_shape.py' # Helper script
    ]
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.py') and file not in exclude_list:
                scripts.append(os.path.join(root, file))
    return sorted(scripts)

def run_script_in_process(script_path, monitor_instance):
    """Runs a single script by importing it and calling its main function."""
    start_time = time.time()
    try:
        # Dynamically import the module
        module_name = os.path.splitext(os.path.basename(script_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module # Add to sys.modules to handle relative imports within the script
        spec.loader.exec_module(module)

        # Find and run the main function
        if hasattr(module, 'main'):
            # Apply the performance decorator to the main function
            timed_main = monitor_instance.time_func(module.main)
            timed_main()
            duration = time.time() - start_time
            return "PASSED", duration, ""
        else:
            duration = time.time() - start_time
            return "NO MAIN", duration, f"Script has no main() function."

    except Exception as e:
        duration = time.time() - start_time
        error_info = f"Exception: {e}\n{traceback.format_exc()}"
        return "CRASHED", duration, error_info

def main():
    """Finds and runs all example scripts, then reports the results."""
    all_scripts = get_all_example_scripts()
    total_scripts = len(all_scripts)
    passed_count = 0
    failed_scripts = []

    # Create a single monitor instance for the entire run
    performance_monitor = PerformanceMonitor()

    print("--- Starting In-Process Run for All Example Scripts ---")
    print(f"Found {total_scripts} scripts to run.\n")

    for i, script in enumerate(all_scripts):
        print(f"[{i+1}/{total_scripts}] Running: {script}...", end=' ', flush=True)
        status, duration, error_info = run_script_in_process(script, performance_monitor)
        print(f"[{status}] ({duration:.2f}s)")

        if status == "PASSED":
            passed_count += 1
        else:
            failed_scripts.append((script, status, error_info))

    # Finalize and print the performance summary
    performance_monitor.finalize_metrics()
    print("\n--- Performance Summary ---")
    print(performance_monitor.generate_report())

    print("\n--- Test Run Summary ---")
    print(f"Total Scripts: {total_scripts}")
    print(f"Passed: {passed_count}")
    print(f"Failed/Crashed: {len(failed_scripts)}")

    if failed_scripts:
        print("\n--- Details of Failed Scripts ---")
        for script, status, error_info in failed_scripts:
            print(f"\n-------------------------------------")
            print(f"Script: {script}")
            print(f"Status: {status}")
            print(f"Details:\n{error_info}")
            print(f"-------------------------------------")
        # Exit with a non-zero code to indicate failure for CI/CD systems
        sys.exit(1)
    else:
        print("\nAll example scripts ran successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
