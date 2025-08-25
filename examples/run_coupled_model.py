"""
Example: Running a Coupled Hydrological-Hydraulic Model
=======================================================

This script demonstrates how to use the SimulationController to build and
run a simple coupled model.

The model consists of two components:
1. A hydrological catchment model (`hydro_model`) that generates runoff.
2. A hydraulic river model (`preissmann_model`) that receives the runoff
   as its upstream inflow.
"""
import numpy as np

# --- Import Framework Components ---
from common.controller import SimulationController
from common.base_model import BaseModelComponent

# --- Import Hydrological Model Components ---
from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SCSCurveNumberModule
from hydro_model.routing import SimpleRouting

# --- Import Hydraulic Model Components ---
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection

def main():
    print("--- 1. Setting up coupled model components ---")

    # --- Hydrological Component: A Catchment ---
    # This catchment will generate runoff from rainfall.
    runoff_mod = SCSCurveNumberModule(CN=75)
    routing_mod = SimpleRouting(k_q=0.8, k_s=0.2)
    catchment = HydrologicalModel(
        name="C1_main_catchment",
        runoff_module=runoff_mod,
        routing_module=routing_mod
    )
    print(f"Created hydrological component: '{catchment.name}'")

    # --- Hydraulic Component: A River Reach ---
    # This river will receive the flow from the catchment.
    num_nodes = 11
    reach_geom = RiverReach(
        cross_sections=[RectangularCrossSection(width=15) for _ in range(num_nodes)],
        lengths=np.full(num_nodes - 1, 500.0),
        slope=0.002,
        manning_n=0.035
    )
    # Downstream water level is fixed for this example
    downstream_level = 1.5 # meters
    river = HydraulicModel(
        name="R1_main_river",
        reach=reach_geom,
        dt=60.0, # Note: dt is set here for the component
        downstream_level=downstream_level
    )
    # Set initial conditions for the river
    river.Q[:] = 0.1 # Small baseflow
    river.Z[:] = downstream_level
    print(f"Created hydraulic component: '{river.name}'")

    # --- 2. Build and Connect the Network ---
    print("\n--- 2. Building simulation network ---")
    controller = SimulationController()
    controller.add_component(catchment)
    controller.add_component(river)

    # Connect the outflow of the catchment to the inflow of the river
    controller.connect("C1_main_catchment", "R1_main_river")
    print("Connected 'C1_main_catchment' -> 'R1_main_river'")

    # --- 3. Define Simulation Inputs ---
    print("\n--- 3. Defining simulation inputs ---")
    num_steps = 120 # 120 steps * 60s/step = 2 hours of simulation
    dt_controller = 60.0 # seconds

    # Global inputs: A simple storm event
    rainfall_hydrograph = np.zeros(num_steps)
    rainfall_hydrograph[10:40] = 15.0 # 15 mm/hr for 30 minutes

    global_inputs = {
        'rainfall': rainfall_hydrograph,
        'pet': np.full(num_steps, 0.1) # Constant potential evapotranspiration
    }
    print(f"Defined a {num_steps}-step simulation with a rainfall pulse.")

    # --- 4. Run the Simulation ---
    controller.run(
        num_steps=num_steps,
        dt=dt_controller,
        global_inputs=global_inputs
    )

    # --- 5. Inspect Final State ---
    print("\n--- 5. Final Model State ---")
    final_catchment_outflow = catchment.get_outflow()
    final_river_outflow = river.get_outflow()

    print(f"Final outflow from '{catchment.name}': {final_catchment_outflow:.3f} m^3/s (Note: units depend on hydro model impl.)")
    print(f"Final outflow from '{river.name}': {final_river_outflow:.3f} m^3/s")
    print("\nFinal state of river reach:")
    print("Node | Water Elev (m) | Discharge (m^3/s)")
    print("---- | -------------- | -----------------")
    for i in range(river.num_nodes):
        print(f"{i:4d} | {river.Z[i]:14.3f} | {river.Q[i]:17.3f}")

if __name__ == "__main__":
    main()
