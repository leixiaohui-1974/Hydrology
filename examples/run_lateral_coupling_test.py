"""
Example: Running a 1D-2D Laterally Coupled Model
=================================================

This script demonstrates how to couple a 1D river model with a 2D
floodplain model using the LateralLink component and the explicit scheduler.
"""
import numpy as np

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from model_2d.mesh import Mesh
from model_2d.model import Model2D
from common.lateral_link import LateralLink
from common.controller import SimulationController

def main():
    print("--- 1. Setting up 1D-2D coupled model ---")

    # --- Component 1: The 1D River ---
    river_nodes = 11
    river_reach = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(river_nodes)],
        lengths=np.full(river_nodes - 1, 100.0),
        slope=0.001,
        manning_n=0.03
    )
    river = HydraulicModel(
        name="main_river",
        reach=river_reach,
        dt=0.5, # Internal dt for the 1D solver
        downstream_level=2.0
    )
    river.Z[:] = 2.5

    # --- Component 2: The 2D Floodplain ---
    points = [(0,0), (1,0), (0,1), (1,1)]; triangles = [(0,1,2), (1,3,2)]
    fp_mesh = Mesh()
    fp_mesh.build_from_points_and_triangles(points, triangles)
    fp_mesh.faces[0].h = 0.01; fp_mesh.faces[1].h = 0.01
    floodplain = Model2D(name="floodplain", mesh=fp_mesh)

    # --- Component 3: The Lateral Link ---
    link = LateralLink(
        name="levee_link",
        model_1d=river, node_1d_idx=5,
        model_2d=floodplain, face_2d_idx=0,
        crest_elevation=2.8, width=10.0, weir_coeff=1.6
    )
    print("Components created and configured.")

    # --- 2. Set up the Simulation Controller ---
    controller = SimulationController()
    controller.add_component(river)
    controller.add_component(floodplain)
    controller.add_component(link) # Add the link as a component

    # --- 3. Run the Simulation ---
    num_steps = 500
    dt_controller = 0.5

    inflow_hydrograph = np.full(num_steps, 20.0)
    inflow_hydrograph[50:200] = 80.0
    global_inputs = {
        "main_river": { "Q_inflow": inflow_hydrograph }
    }

    print("\n--- 2. Running simulation ---")
    for status in controller.run(num_steps, dt_controller, global_inputs):
        if (status['step']) % 100 == 0:
            print(f"\n--- Step {status['step']} ---")
            print(f"River Z at link: {river.Z[link.node_1d_idx]:.3f} m")
            print(f"Floodplain h at link: {floodplain.mesh.faces[link.face_2d_idx].h:.3f} m")
            print(f"Exchange flow (to 2D): {link.outflow_to_2d:.3f} m^3/s")

    print("\n--- 3. Simulation Finished ---")

if __name__ == "__main__":
    main()
