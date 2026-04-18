"""
Generic Simulation Runner from Configuration File
=================================================

This script runs a simulation defined in a YAML configuration file.

Usage:
    python3 run_from_config.py <path_to_config.yaml>
"""
import argparse
import sys
import logging
from datetime import datetime
from pathlib import Path

from common.config_parser import ConfigParser
from common.program_contract_bridge import CONTRACTS_AVAILABLE
from common.program_contract_outputs import (
    build_workflow_run_payload,
    default_workflow_run_output,
    write_workflow_run_metadata,
)


def _build_arg_parser():
    parser = argparse.ArgumentParser(description="Run a simulation from a YAML configuration file.")
    parser.add_argument("config_file", help="Path to YAML configuration file")
    parser.add_argument("--run-id", default=None, help="Override workflow run id")
    parser.add_argument("--case-id", default="adhoc", help="Case identifier for workflow metadata")
    parser.add_argument("--workflow-type", default="hydrological_simulation", help="Workflow type for metadata")
    parser.add_argument(
        "--metadata-out",
        default=None,
        help="Optional output path for workflow_run JSON metadata",
    )
    return parser

def main():
    """
    Main execution function.
    """
    args = _build_arg_parser().parse_args()
    config_file = args.config_file
    started_at = datetime.utcnow().replace(microsecond=0).isoformat()
    run_id = args.run_id or f"hydrology-run-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

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
    for status in controller.run(
        num_steps=num_steps,
        dt=dt,
        global_inputs=global_inputs
    ):
        # Currently, we only ensure the generator is fully consumed to drive the simulation.
        # Future extensions may collect or stream these status updates.
        pass

    print("\n--- Final State of All Components ---")
    for name, component in controller.components.items():
        outflow = component.get_outflow()
        print(f"Component: '{name}', Final Outflow: {outflow:.3f}")

    completed_at = datetime.utcnow().replace(microsecond=0).isoformat()
    if CONTRACTS_AVAILABLE:
        metadata_path = Path(args.metadata_out) if args.metadata_out else default_workflow_run_output(config_file)
        payload = build_workflow_run_payload(
            run_id=run_id,
            case_id=args.case_id,
            workflow_type=args.workflow_type,
            status="completed",
            config_path=config_file,
            components=[c.name for c in controller.components.values()],
            dt_seconds=dt,
            num_steps=num_steps,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "global_input_keys": sorted(global_inputs.keys()) if isinstance(global_inputs, dict) else [],
                "metadata_out": str(metadata_path),
            },
        )
        write_workflow_run_metadata(metadata_path, payload)
        print(f"\n--- Workflow metadata written to: {metadata_path} ---")

if __name__ == "__main__":
    main()
