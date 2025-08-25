"""
Example: Running a Looped Network Model
=======================================

This script demonstrates how to use the SimulationController to build and
run a model with a simple looped network to test the iterative solver.

The model consists of three river reaches connected in a ring:
A -> B -> C -> A
"""
import numpy as np

from common.controller import SimulationController
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection

def create_river(name, num_nodes=5, length=500.0, slope=0.001):
    """Helper function to create a simple river component."""
    reach_geom = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(num_nodes)],
        lengths=np.full(num_nodes - 1, length / (num_nodes - 1)),
        slope=slope,
        manning_n=0.03
    )
    # The downstream level for these will be dynamically set by the upstream component
    river = HydraulicModel(
        name=name,
        reach=reach_geom,
        dt=10.0,
        downstream_level=2.0
    )
    return river

def main():
    print("--- 1. Setting up looped network model ---")

    # --- Create Components ---
    river_A = create_river("river_A")
    river_B = create_river("river_B")
    river_C = create_river("river_C")

    # Set some initial conditions to get the water moving
    river_A.Q[:] = 5.0
    river_A.Z[:] = 2.5
    river_B.Z[:] = 2.2
    river_C.Z[:] = 2.0

    print("Created components: river_A, river_B, river_C")

    # --- 2. Build and Connect the Network in a Loop ---
    print("\n--- 2. Building simulation network ---")
    controller = SimulationController()
    controller.add_component(river_A)
    controller.add_component(river_B)
    controller.add_component(river_C)

    # Connect in a ring: A -> B -> C -> A
    controller.connect("river_A", "river_B")
    controller.connect("river_B", "river_C")
    controller.connect("river_C", "river_A")
    print("Network connected: A -> B -> C -> A")

    # --- 3. Run the Simulation ---
    num_steps = 30
    dt_controller = 10.0

    # No global inputs, this is a closed loop system
    # We must iterate over the generator to make it execute.
    for status in controller.run(
        num_steps=num_steps,
        dt=dt_controller,
        global_inputs=None
    ):
        # We can inspect the status here if needed, but for this test,
        # we just need to consume the generator to make it run.
        pass

    # --- 4. Inspect Final State ---
    print("\n--- 4. Final Model State ---")
    print(f"Final outflow from river_A: {river_A.get_outflow():.3f} m^3/s")
    print(f"Final outflow from river_B: {river_B.get_outflow():.3f} m^3/s")
    print(f"Final outflow from river_C: {river_C.get_outflow():.3f} m^3/s")

    print("\nVerification:")
    print("Check the log output above for 'Cycle detected' and 'Loop converged' messages.")
    print("If the simulation ran to completion without errors, the test is successful.")

if __name__ == "__main__":
    main()
