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

        # 1. Create a simple 2x1 mesh (2 square cells, 4 triangular faces)
        mesh = Mesh()
        points = np.array([
            [0, 0], [1, 0], [2, 0],
            [0, 1], [1, 1], [2, 1]
        ])
        triangles = np.array([
            [0, 1, 4], [0, 4, 3],
            [1, 2, 5], [1, 5, 4]
        ])
        mesh.build_from_points_and_triangles(points, triangles)

        # 2. Set initial conditions
        # Uniform water depth, zero momentum. Tilted bed: z = -0.1 * x
        for face in mesh.faces:
            face.h = 1.0
            face.uh = 0.0
            face.vh = 0.0
            # Set bed elevation based on the face centroid's x-coordinate
            face.z_bed = -0.1 * face.centroid[0]

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

        # Check momentum for a face in the middle to avoid boundary effects
        # Face 0 is triangle (0,1,4), centroid x is 2/3.
        # Face 1 is triangle (0,4,3), centroid x is 1/3.
        # Face 2 is triangle (1,2,5), centroid x is 4/3.
        # Face 3 is triangle (1,5,4), centroid x is 5/3.
        uh_face0 = mesh.faces[0].uh
        vh_face0 = mesh.faces[0].vh

        self.assertGreater(uh_face0, 0) # uh should be positive
        self.assertAlmostEqual(vh_face0, 0, places=5)

        # Also check the total momentum
        self.assertGreater(total_uh, 0)
        self.assertAlmostEqual(total_vh, 0, places=5)

        print("Tilted bed source term test passed.")

        print("Tilted bed source term test passed.")

if __name__ == '__main__':
    unittest.main()
