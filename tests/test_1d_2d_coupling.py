import unittest
import sys
import os
import numpy as np

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.cross_section import RectangularCrossSection
from model_2d.model import Model2D
from model_2d.mesh import Mesh
from common.controller import SimulationController
from common.lateral_link import LateralWeirLink

class Test1D2DCoupling(unittest.TestCase):

    def setUp(self):
        """Set up the coupled model components for testing."""
        # 1. Create a simple 1D model
        num_nodes = 5
        cross_sections = [RectangularCrossSection(width=10) for _ in range(num_nodes)]
        reach = RiverReach(
            cross_sections=cross_sections,
            lengths=np.full(num_nodes - 1, 250.0),
            slope=0.001,
            manning_n=0.03
        )
        # Initial Z is water surface elevation. Z_bed will be calculated from slope.
        # Let's set Z high enough to be above the bank.
        initial_Z = [11.0, 11.1, 11.2, 11.3, 11.4]
        self.model_1d = HydraulicModel(
            name="TestRiver",
            reach=reach,
            dt=10.0,
            downstream_level=initial_Z[-1], # Consistent downstream boundary
            initial_Z=initial_Z
        )

        # 2. Create a simple 2D model
        mesh = Mesh()
        points = np.array([[0, 20], [100, 20], [0, 120], [100, 120]])
        triangles = np.array([[0, 1, 3], [0, 3, 2]])
        mesh.build_from_points_and_triangles(points, triangles)
        # Set all z_bed and initial water levels to 9.0
        for face in mesh.faces:
            face.z_bed = 9.0
            face.h = 0.0 # Initially dry
        self.model_2d = Model2D(name="TestFloodplain", mesh=mesh)

        # 3. Create the lateral link
        # Connect middle node of 1D reach to a boundary edge of 2D mesh
        # For simplicity, we assume edge 0 is a boundary edge we can use
        self.link_node_1d = 2
        self.link_edge_2d = 0
        self.model_2d.mesh.set_boundary_edge_type(self.link_edge_2d, 'flow')

        self.link = LateralWeirLink(
            name="TestLink",
            model_1d=self.model_1d,
            model_2d=self.model_2d,
            reach_id="main_reach", # Placeholder
            node_idx_1d=self.link_node_1d,
            edge_ids_2d=[self.link_edge_2d],
            weir_coeff=1.6,
            bank_elevation=10.5 # Water level in 1D model (11.2) is above this
        )

        # 4. Set up the controller
        self.controller = SimulationController()
        self.controller.add_component(self.model_1d)
        self.controller.add_component(self.model_2d)
        self.controller.add_link(self.link)

    def test_mass_conservation_1d_to_2d(self):
        """
        Tests that water flowing from the 1D model to the 2D model is conserved.
        """
        print("\nRunning test_mass_conservation_1d_to_2d...")

        # Calculate initial water volume
        vol_1d_initial = np.sum(self.model_1d.reach.areas_from_Z(self.model_1d.Z, self.model_1d.Z_bed) * self.model_1d.reach.lengths_for_volume())
        vol_2d_initial = np.sum([f.h * f.area for f in self.model_2d.mesh.faces])
        vol_total_initial = vol_1d_initial + vol_2d_initial

        # Run two steps.
        # Step 1: lateral flow is 0, but a non-zero exchange flow is calculated for the next step.
        # Step 2: the calculated exchange flow is applied, and water volume should change.
        i = 0
        for _ in self.controller.run(num_steps=2, dt=10.0):
            print(f"\n--- End of Step {i+1} ---")
            print(f"1D Water Levels (Z): {self.model_1d.Z}")
            print(f"2D Water Depth (h): {[f.h for f in self.model_2d.mesh.faces]}")
            print(f"Flow calculated for next step: {self.link.exchange_flow}")
            i += 1

        # Calculate final water volume
        vol_1d_final = np.sum(self.model_1d.reach.areas_from_Z(self.model_1d.Z, self.model_1d.Z_bed) * self.model_1d.reach.lengths_for_volume())
        vol_2d_final = np.sum([f.h * f.area for f in self.model_2d.mesh.faces])
        vol_total_final = vol_1d_final + vol_2d_final

        print(f"Initial Volume: 1D={vol_1d_initial:.4f}, 2D={vol_2d_initial:.4f}, Total={vol_total_initial:.4f}")
        print(f"Final Volume:   1D={vol_1d_final:.4f}, 2D={vol_2d_final:.4f}, Total={vol_total_final:.4f}")
        print(f"Exchange Flow Q: {self.link.exchange_flow:.4f}")

        # Assertions
        self.assertGreater(self.link.exchange_flow, 0, "Exchange flow should be positive (1D -> 2D)")
        self.assertLess(vol_1d_final, vol_1d_initial, "1D model volume should decrease")
        self.assertGreater(vol_2d_final, vol_2d_initial, "2D model volume should increase")

        # Check that the mass balance error is within an acceptable relative tolerance (e.g., 0.1%)
        relative_error = abs(vol_total_initial - vol_total_final) / vol_total_initial if vol_total_initial > 1e-6 else 0
        self.assertLess(relative_error, 0.001, f"Total volume should be conserved within a 0.1% tolerance, but relative error was {relative_error:.4f}")

if __name__ == '__main__':
    unittest.main()
