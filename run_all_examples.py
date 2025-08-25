import os
import subprocess
import sys
import time

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

def run_script(script_path, timeout=60):
    """Runs a single script using subprocess and returns its status."""
    start_time = time.time()
    try:
        # We use sys.executable to ensure we're using the same python interpreter
        process = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False # Do not raise exception on non-zero exit code
        )
        end_time = time.time()
        duration = end_time - start_time

        # Check for common signs of failure in stderr, even if exit code is 0
        stderr = process.stderr.lower()
        has_error = "error" in stderr or "traceback" in stderr or "failed" in stderr

        if process.returncode == 0 and not has_error:
            return "PASSED", duration, ""
        else:
            error_summary = f"Exit Code: {process.returncode}\n--- STDOUT ---\n{process.stdout[-500:]}\n--- STDERR ---\n{process.stderr}"
            return "FAILED", duration, error_summary

    except subprocess.TimeoutExpired:
        end_time = time.time()
        duration = end_time - start_time
        return "TIMEOUT", duration, f"Process timed out after {timeout} seconds."
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        return "CRASHED", duration, str(e)

def main():
    """Finds and runs all example scripts, then reports the results."""
    all_scripts = get_all_example_scripts()
    total_scripts = len(all_scripts)
    passed_count = 0
    failed_scripts = []

    print("--- Starting Test Run for All Example Scripts ---")
    print(f"Found {total_scripts} scripts to run.\n")

    for i, script in enumerate(all_scripts):
        print(f"[{i+1}/{total_scripts}] Running: {script}...", end=' ', flush=True)
        status, duration, error_info = run_script(script)
        print(f"[{status}] ({duration:.2f}s)")

        if status == "PASSED":
            passed_count += 1
        else:
            failed_scripts.append((script, status, error_info))

    print("\n--- Test Run Summary ---")
    print(f"Total Scripts: {total_scripts}")
    print(f"Passed: {passed_count}")
    print(f"Failed/Timeout/Crashed: {len(failed_scripts)}")

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
