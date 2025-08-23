import unittest
import sys
import os
import numpy as np

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model_2d.mesh import Mesh
from model_2d.solver import finite_volume_step

class Test2DSolver(unittest.TestCase):

    def test_tilted_bed_source_term(self):
        """
        Tests if the bed slope source term correctly generates momentum on a
        tilted plane with initially still water.
        """
        print("\nRunning test_tilted_bed_source_term...")

        # 1. Create a simple 1x2 mesh (a square made of 2 triangles)
        mesh = Mesh()
        points = np.array([
            [0, 0], [1, 0],
            [0, 1], [1, 1]
        ])
        triangles = np.array([
            [0, 1, 3],  # Bottom-right triangle
            [0, 3, 2]   # Top-left triangle
        ])
        mesh.build_from_points_and_triangles(points, triangles)

        # 2. Set initial conditions
        # Uniform water depth, zero momentum. Tilted bed: z = -0.1 * x
        for node in mesh.nodes:
            node.z = -0.1 * node.x

        # Recalculate face z_bed after setting node elevations and set water depth
        for face in mesh.faces:
            face.z_bed = (face.nodes[0].z + face.nodes[1].z + face.nodes[2].z) / 3.0
            # Set a constant water surface elevation initially, so depth varies
            face.h = max(0, 1.0 - face.z_bed)
            face.uh = 0.0
            face.vh = 0.0

        # 3. Run the solver for one step
        dt = 0.01
        finite_volume_step(mesh, dt)

        # 4. Assert results
        # All faces should have gained positive x-momentum (uh) because the
        # slope is negative (g*h*(-dz/dx) = g*h*(-(-0.1)) = positive).
        # The y-momentum (vh) should remain close to zero.

        total_uh = sum(f.uh for f in mesh.faces)
        total_vh = sum(f.vh for f in mesh.faces)

        print(f"Total momentum after one step: uh={total_uh:.6f}, vh={total_vh:.6f}")

        # For this simple mesh, both faces should behave similarly.
        # We check face 0.
        uh_face0 = mesh.faces[0].uh
        vh_face0 = mesh.faces[0].vh

        self.assertGreater(uh_face0, 0) # uh should be positive
        self.assertAlmostEqual(vh_face0, 0, places=5)

        print("Tilted bed source term test passed.")

        print("Tilted bed source term test passed.")

if __name__ == '__main__':
    unittest.main()
