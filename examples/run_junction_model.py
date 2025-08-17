"""
Example: Running a Network Model with a Junction
================================================

This script demonstrates how to use the SimulationController to build and
run a network model with a junction where two rivers merge.

The model consists of four components:
1. Two upstream hydraulic river models (`river_A`, `river_B`).
2. A junction (`J1`) that merges their flow.
3. A downstream hydraulic river model (`river_C`) that receives the merged flow.
"""
import numpy as np

from common.controller import SimulationController
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from common.junction import Junction

def create_river(name, num_nodes=5, length=500.0, slope=0.001):
    """Helper function to create a simple river component."""
    reach_geom = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(num_nodes)],
        lengths=np.full(num_nodes - 1, length / (num_nodes - 1)),
        slope=slope,
        manning_n=0.03
    )
    river = HydraulicModel(
        name=name,
        reach=reach_geom,
        dt=10.0,
        downstream_level=2.0 # Default downstream level
    )
    river.Q[:] = 0.1 # Small baseflow
    river.Z[:] = 2.5
    return river

def main():
    print("--- 1. Setting up network model components ---")

    # --- Create Components ---
    river_A = create_river("river_A")
    river_B = create_river("river_B")
    junction = Junction(name="J1")
    river_C = create_river("river_C", num_nodes=11, length=1000.0)

    print("Created components: river_A, river_B, J1, river_C")

    # --- 2. Build and Connect the Network ---
    print("\n--- 2. Building simulation network ---")
    controller = SimulationController()
    # Add in execution order: upstream reaches first, then junction, then downstream
    controller.add_component(river_A)
    controller.add_component(river_B)
    controller.add_component(junction)
    controller.add_component(river_C)

    controller.connect("river_A", "J1")
    controller.connect("river_B", "J1")
    controller.connect("J1", "river_C")
    print("Network connected: (river_A, river_B) -> J1 -> river_C")

    # --- 3. Define Simulation Inputs ---
    num_steps = 50
    dt_controller = 10.0

    # We will provide inflows for the two headwater rivers
    global_inputs = {
        'river_A': {'Q_inflow': np.full(num_steps, 10.0)},
        'river_B': {'Q_inflow': np.full(num_steps, 15.0)}
    }
    print("Defined inflows for river_A (10) and river_B (15)")

    # --- 4. Custom Run Loop ---
    # The controller's run method needs slight adaptation for component-specific inputs
    print("\n--- 4. Running simulation ---")
    for t in range(num_steps):
        print(f"--- Controller: Time step {t+1}/{num_steps} ---")

        inflows_for_step = {name: {} for name in controller.components}

        # Add component-specific global inputs
        for comp_name, inputs in global_inputs.items():
            for key, values in inputs.items():
                inflows_for_step[comp_name][key] = values[t]

        for component_name in controller.execution_order:
            parent_names = controller.parents.get(component_name, [])
            for parent_name in parent_names:
                parent_component = controller.components[parent_name]
                if isinstance(parent_component, Junction):
                    downstream_connections = controller.network.get(parent_name, [])
                    parent_component.get_outflows(downstream_connections)
                    inflows_for_step[component_name][parent_name] = parent_component.outflows.get(component_name, 0.0)
                else:
                    inflows_for_step[component_name][parent_name] = parent_component.get_outflow()

            component = controller.components[component_name]
            component.step(inflows_for_step[component_name], dt_controller)

    print("--- Simulation Finished ---")

    # --- 5. Inspect Final State & Verify ---
    print("\n--- 5. Final Model State ---")
    outflow_A = river_A.get_outflow()
    outflow_B = river_B.get_outflow()
    total_inflow_to_J1 = junction.total_inflow
    outflow_J1 = junction.get_outflow()
    inflow_to_C = total_inflow_to_J1 # This is what should have been passed to river_C

    print(f"Final outflow from river_A: {outflow_A:.3f} m^3/s")
    print(f"Final outflow from river_B: {outflow_B:.3f} m^3/s")
    print(f"Total inflow to J1 at final step: {total_inflow_to_J1:.3f} m^3/s")
    print(f"Final outflow from river_C: {river_C.get_outflow():.3f} m^3/s")

    # Verification
    print("\n--- Verification ---")
    print(f"Is inflow to J1 ({total_inflow_to_J1:.3f}) approximately equal to the sum of "
          f"outflows from A and B ({outflow_A + outflow_B:.3f})?")
    assert np.isclose(total_inflow_to_J1, outflow_A + outflow_B), "Junction mass balance failed!"
    print("Mass balance at junction is CORRECT.")

if __name__ == "__main__":
    main()
