import numpy as np
import matplotlib.pyplot as plt

# Import all the components and the controller
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from model_2d.model import Model2D
from model_2d.mesh import Mesh
from common.lateral_link import LateralLink
from common.controller import ImplicitSimulationController
# I need to create this file for the boundary condition
from common.boundary_conditions import InflowBC

def run_implicit_coupling_test():
    """
    The final, integrated test case for the semi-implicit 1D-2D coupling.
    """
    print("--- Setting up Semi-Implicit 1D-2D Coupling Test ---")

    # Simulation parameters
    dt = 10.0  # seconds
    num_steps = 360

    # 1. Define the 1D River Model Component
    n_nodes = 11
    reach = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(n_nodes)],
        lengths=np.full(n_nodes - 1, 100.0),
        slope=1e-4,
        manning_n=0.03
    )
    river_model = HydraulicModel(
        name="MainRiver",
        reach=reach,
        downstream_level=4.8
    )
    river_model.Z[:] = 5.0 # Initial water level

    # Define and set the upstream boundary condition
    inflow_bc = InflowBC(name="RiverInflow", discharge_func=lambda t: 40.0)
    river_model.set_upstream_bc(inflow_bc)

    # 2. Define the 2D Floodplain Model Component
    floodplain_mesh = Mesh()
    floodplain_mesh.build_from_points_and_triangles(
        points=[(0, 50), (400, 50), (0, 150), (400, 150)],
        triangles=[(0, 1, 2), (1, 3, 2)]
    )
    for face in floodplain_mesh.faces:
        face.z_bed = 5.5
        face.h = 1e-3

    floodplain = Model2D(name="Floodplain", mesh=floodplain_mesh)

    # 3. Define the Lateral Link Component
    link = LateralLink(
        name="LeveeSpill",
        model_1d=river_model,
        link_1d_node_idx=5,
        model_2d=floodplain,
        link_2d_face_idx=0,
        weir_crest_level=5.2,
        weir_length=100.0,
        weir_coefficient=1.0
    )

    # 4. Set up and run the Simulation Controller
    # The order matters for how variables are laid out in the matrix
    components = [river_model, floodplain, link]
    controller = ImplicitSimulationController(components=components, dt=dt)

    print("--- Starting Simulation ---")
    for progress in controller.run(num_steps=num_steps):
        if (progress['step'] % 100 == 0):
            print(f"   ...step {progress['step']}/{progress['num_steps']}")
    print("--- Simulation Finished ---")

    # 5. Plotting Results
    print("--- Plotting Results ---")
    results = controller.get_results()
    river_results = results[river_model.name]
    floodplain_results = results[floodplain.name]
    link_results = results[link.name]

    time_steps = np.arange(0, (num_steps + 1) * dt, dt)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    fig.suptitle("Semi-Implicit 1D-2D Coupling Test Results")

    # Plot 1: Water levels
    ax1.set_title("Water Levels at Connection Point")
    river_water_level = river_results['H'][:, link.link_1d_node_idx]

    link_face_idx = link.link_2d_face_idx
    floodplain_h = floodplain_results['h'][:, link_face_idx]
    floodplain_z_bed = floodplain.mesh.faces[link_face_idx].z_bed
    floodplain_water_level = floodplain_h + floodplain_z_bed

    ax1.plot(time_steps, river_water_level, label=f"River Node {link.link_1d_node_idx} Water Level")
    ax1.plot(time_steps, floodplain_water_level, label=f"Floodplain Face {link_face_idx} Water Level")
    ax1.axhline(y=link.weir_crest_level, color='r', linestyle='--', label=f"Weir Crest ({link.weir_crest_level}m)")
    ax1.set_ylabel("Water Level (m)")
    ax1.legend()
    ax1.grid(True)

    # Plot 2: Flow over link
    ax2.set_title("Flow Exchange over Lateral Link")
    # The history includes the initial state, so it's num_steps + 1 long.
    ax2.plot(time_steps, link_results['Q'], label="Flow from River to Floodplain")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Discharge (m^3/s)")
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output_filename = "implicit_coupling_results.png"
    plt.savefig(output_filename)
    print(f"Results plot saved to {output_filename}")
    plt.show()

if __name__ == "__main__":
    run_implicit_coupling_test()
