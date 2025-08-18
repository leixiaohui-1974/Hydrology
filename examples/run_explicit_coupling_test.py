import numpy as np
import matplotlib.pyplot as plt

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from model_2d.model import Model2D
from model_2d.mesh import Mesh
from common.lateral_link import LateralLink
from common.controller import SimulationController

def run_explicit_coupling_test():
    """
    An integrated test case for the EXPLICIT 1D-2D lateral coupling scheme.
    This test verifies that the components can be created and stepped by the
    explicit controller.
    """
    print("--- Setting up Explicit 1D-2D Coupling Test ---")

    # Simulation parameters
    dt = 5  # seconds
    num_steps = int(3600 / dt)

    # 1. Define the 1D River Model
    L = 1000
    n_nodes = 11
    dx = L / (n_nodes - 1)

    river_reach = RiverReach(
        cross_sections=[RectangularCrossSection(width=10) for _ in range(n_nodes)],
        lengths=np.full(n_nodes - 1, dx),
        slope=1e-4,
        manning_n=0.03
    )

    river_model = HydraulicModel(
        name="MainRiver",
        reach=river_reach,
        downstream_level=4.8
    )
    # Set initial water level higher than downstream to see it drop
    river_model.Z[:] = 5.0

    # 2. Define the 2D Floodplain Model
    floodplain_mesh = Mesh()
    floodplain_mesh.build_from_points_and_triangles(
        points=[(0, 50), (400, 50), (0, 150), (400, 150)],
        triangles=[(0, 1, 2), (1, 3, 2)]
    )
    for face in floodplain_mesh.faces:
        face.z_bed = 5.5 # Higher than initial river level
        face.h = 1e-3

    floodplain = Model2D(
        name="Floodplain",
        mesh=floodplain_mesh
    )

    # 3. Define the Lateral Link
    link = LateralLink(
        name="LeveeSpill",
        model_1d=river_model,
        node_1d_idx=5,
        model_2d=floodplain,
        face_2d_idx=0,
        crest_elevation=5.2,
        width=100.0,
        weir_coeff=1.0
    )

    # 4. Set up the Simulation Controller
    controller = SimulationController()
    controller.add_component(river_model)
    controller.add_component(floodplain)
    controller.add_component(link)

    # 5. Define global inputs (upstream inflow hydrograph)
    inflow_q = 40.0 # m^3/s
    inflow_hydrograph = [inflow_q for _ in range(num_steps)]
    global_inputs = {
        "MainRiver": {
            "Q_inflow": inflow_hydrograph
        }
    }

    # 6. Run the simulation
    print("--- Starting Simulation ---")
    river_z_history = [river_model.Z.copy()]
    floodplain_h_history = [[f.h for f in floodplain.mesh.faces]]
    link_q_history = []

    for progress in controller.run(num_steps=num_steps, dt=dt, global_inputs=global_inputs):
        river_z_history.append(river_model.Z.copy())
        floodplain_h_history.append([f.h for f in floodplain.mesh.faces])
        link_q_history.append(link.outflow)
        if (progress['step'] % 100 == 0):
            print(f"   ...step {progress['step']}/{progress['num_steps']}")

    print("--- Simulation Finished ---")

    # 7. Plotting Results
    print("--- Plotting Results ---")
    river_z_history = np.array(river_z_history)
    floodplain_h_history = np.array(floodplain_h_history)
    link_q_history = np.array(link_q_history)
    time_steps = np.arange(0, (num_steps + 1) * dt, dt)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    fig.suptitle("Explicit 1D-2D Coupling Test Results")

    # Plot 1: Water levels
    ax1.set_title("Water Levels at Connection Point")
    river_water_level = river_z_history[:, link.node_1d_idx]

    link_face_idx = link.face_2d_idx
    floodplain_water_level = floodplain_h_history[:, link_face_idx] + floodplain.mesh.faces[link_face_idx].z_bed

    ax1.plot(time_steps, river_water_level, label=f"River Node {link.node_1d_idx} Water Level")
    ax1.plot(time_steps, floodplain_water_level, label=f"Floodplain Face {link_face_idx} Water Level")
    ax1.axhline(y=link.crest_elevation, color='r', linestyle='--', label=f"Weir Crest ({link.crest_elevation}m)")
    ax1.set_ylabel("Water Level (m)")
    ax1.legend()
    ax1.grid(True)

    # Plot 2: Flow over link
    ax2.set_title("Flow Exchange over Lateral Link")
    ax2.plot(time_steps[:-1], link_q_history, label="Flow from River to Floodplain")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Discharge (m^3/s)")
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output_filename = "explicit_coupling_results.png"
    plt.savefig(output_filename)
    print(f"Results plot saved to {output_filename}")
    plt.show()

if __name__ == "__main__":
    run_explicit_coupling_test()
