"""
Example: Running the 2D Hydrodynamic Model (Proof-of-Concept)
=============================================================

This script demonstrates how to set up and run the basic 2D solver
for a simple "dam break" scenario on a coarse, rectangular mesh.
"""
import sys
import os
import numpy as np

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from model_2d.mesh import Mesh
from model_2d.model import Model2D

def main():
    print("--- 1. Setting up 2D model test case ---")

    # --- Define a simple mesh (3x2 grid of squares, 6 cells, 12 triangles) ---
    points = [
        (0,0), (1,0), (2,0), (3,0), # Row 1
        (0,1), (1,1), (2,1), (3,1), # Row 2
        (0,2), (1,2), (2,2), (3,2)  # Row 3
    ]

    triangles = [
        (0,1,4), (1,5,4), # Square 1
        (1,2,5), (2,6,5), # Square 2
        (2,3,6), (3,7,6), # Square 3
        (4,5,8), (5,9,8), # Square 4
        (5,6,9), (6,10,9),# Square 5
        (6,7,10),(7,11,10)# Square 6
    ]

    # --- Build the mesh object ---
    mesh = Mesh()
    mesh.build_from_points_and_triangles(points, triangles)

    # --- Set Initial Conditions (Dam Break) ---
    print("Setting up dam break initial conditions...")
    for face in mesh.faces:
        # If the cell's centroid is in the left half (x < 1.5), set high water
        if face.centroid[0] < 1.5:
            face.h = 2.0
        else:
            face.h = 1.0
        # All other state variables (uh, vh, z_bed) are zero

    # --- Instantiate the 2D Model ---
    model = Model2D(name="2D_dam_break", mesh=mesh)

    # --- Run the Simulation ---
    num_steps = 20
    dt = 0.05 # 2D models often require small time steps for stability
    print(f"\n--- 2. Running simulation for {num_steps} steps ---")

    for i in range(num_steps):
        model.step(inflows={}, dt=dt)
        # Print status for a few key cells
        if (i+1) % 5 == 0:
            h_left = model.mesh.faces[0].h
            h_right = model.mesh.faces[-1].h
            print(f"Step {i+1}: Left-most cell depth = {h_left:.3f}, Right-most cell depth = {h_right:.3f}")

    print("\n--- 3. Simulation Finished ---")

    # --- 4. Print Final State ---
    print("\nFinal water depth (h) for each cell:")
    for face in model.mesh.faces:
        print(f"  Cell {face.id:2d} at ({face.centroid[0]:.2f}, {face.centroid[1]:.2f}): h = {face.h:.4f}")

if __name__ == "__main__":
    main()
