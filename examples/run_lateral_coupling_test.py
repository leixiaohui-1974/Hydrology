"""
Example: Running a 1D-2D Laterally Coupled Model
=================================================

This script demonstrates how to couple a 1D river model with a 2D
floodplain model using the LateralLink component and an explicit
coupling scheme managed by a custom run loop.
"""
import numpy as np

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from model_2d.mesh import Mesh
from model_2d.model import Model2D
from common.lateral_link import LateralLink

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
        dt=0.5, # Use a small dt for the component's internal solver
        downstream_level=2.0
    )
    river.Z[:] = 2.5 # Initial water level

    # --- Component 2: The 2D Floodplain ---
    points = [(0,0), (1,0), (0,1), (1,1)]
    triangles = [(0,1,2), (1,3,2)]
    fp_mesh = Mesh()
    fp_mesh.build_from_points_and_triangles(points, triangles)
    fp_mesh.faces[0].h = 0.01 # A little water to avoid instability
    fp_mesh.faces[1].h = 0.01
    floodplain = Model2D(name="floodplain", mesh=fp_mesh)

    # --- Component 3: The Lateral Link ---
    link = LateralLink(
        name="levee_link",
        model_1d=river, node_1d_idx=5,
        model_2d=floodplain, face_2d_idx=0,
        crest_elevation=2.8, # Levee is at 2.8m
        width=10.0,
        weir_coeff=1.6
    )
    print("Components created: river, floodplain, and a lateral link.")

    # --- 2. Run the Simulation with a custom loop ---
    num_steps = 500
    dt = 0.5 # A small time step is crucial for explicit coupling stability

    river_inflow = np.full(num_steps, 20.0)
    river_inflow[50:200] = 80.0 # High flow event to overtop the levee

    print("\n--- 2. Running simulation ---")
    print(f"Initial river Z at link: {river.Z[link.node_1d_idx]:.3f} m")
    print(f"Initial floodplain h at link: {floodplain.mesh.faces[link.face_2d_idx].h:.3f} m")
    print(f"Levee crest elevation: {link.crest_elevation:.3f} m")

    for i in range(num_steps):
        # a. Step the link to calculate exchange flow
        link.step(inflows={}, dt=dt)

        # b. Prepare inflows for the main components
        river_inflows = {
            'Q_inflow': river_inflow[i],
            'lateral': {link.node_1d_idx: link.outflow_to_1d}
        }
        # The 2D model's inflow dict is simpler: {cell_idx: flow}
        floodplain_inflows = {
            link.face_2d_idx: link.outflow_to_2d
        }

        # c. Step the main components
        river.step(river_inflows, dt)
        floodplain.step(floodplain_inflows, dt)

        if (i+1) % 100 == 0:
            print(f"\n--- Step {i+1} ---")
            print(f"River Z at link: {river.Z[link.node_1d_idx]:.3f} m")
            print(f"Floodplain h at link: {floodplain.mesh.faces[link.face_2d_idx].h:.3f} m")
            print(f"Exchange flow (to 2D): {link.outflow_to_2d:.3f} m^3/s")

    print("\n--- 3. Simulation Finished ---")

if __name__ == "__main__":
    main()
