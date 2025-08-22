import numpy as np
import json
from scipy.spatial import Delaunay
from collections import defaultdict
import sys
import os

# Adjust path to import the Mesh class
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model_2d.mesh import Mesh

import argparse

def create_channel_mesh(length=100, width=20, num_x=21, num_y=5, output_path='channel_mesh.json'):
    """
    Generates a simple, unstructured triangular mesh for a rectangular channel.

    Args:
        length (int): Length of the channel.
        width (int): Width of the channel.
        num_x (int): Number of points in the x-direction.
        num_y (int): Number of points in the y-direction.
        output_path (str): Path to save the output JSON mesh file.
    """
    # 1. Create a grid of points
    x = np.linspace(0, length, num_x)
    y = np.linspace(0, width, num_y)
    xv, yv = np.meshgrid(x, y)
    points = np.vstack([xv.ravel(), yv.ravel()]).T

    # 2. Create a Delaunay triangulation from the points
    tri = Delaunay(points)
    triangles = tri.simplices

    print(f"Generated mesh with {len(points)} points and {len(triangles)} triangles.")

    # 3. Identify boundary edges
    # An edge is a boundary if it belongs to only one triangle.
    edge_count = defaultdict(int)
    for t in triangles:
        edge_count[tuple(sorted((t[0], t[1])))] += 1
        edge_count[tuple(sorted((t[1], t[2])))] += 1
        edge_count[tuple(sorted((t[2], t[0])))] += 1

    boundary_point_pairs = [edge for edge, count in edge_count.items() if count == 1]

    # 4. Map point pairs back to edge IDs
    # This requires building the full mesh topology, just like in mesh.py
    # For simplicity, we'll just identify the upstream and downstream edge points

    upstream_points = [i for i, p in enumerate(points) if p[0] == 0]
    downstream_points = [i for i, p in enumerate(points) if p[0] == length]

    upstream_edges = [pair for pair in boundary_point_pairs if pair[0] in upstream_points and pair[1] in upstream_points]
    downstream_edges = [pair for pair in boundary_point_pairs if pair[0] in downstream_points and pair[1] in downstream_points]

    # 4. Build a temporary mesh to find the actual edge IDs
    temp_mesh = Mesh()
    temp_mesh.build_from_points_and_triangles(points, triangles)

    upstream_edge_ids = []
    for edge in temp_mesh.edges:
        # An upstream edge is a boundary edge where both nodes have x=0
        is_upstream = all(node.x == 0 for node in edge.nodes)
        if edge.face2 is None and is_upstream:
            upstream_edge_ids.append(edge.id)

    print("\n--- Boundary Info ---")
    print(f"Identified {len(upstream_edge_ids)} upstream boundary edges.")
    print(f"Upstream Edge IDs for config.yaml: {upstream_edge_ids}")


    # 5. Save to JSON
    mesh_data = {
        "points": points.tolist(),
        "triangles": triangles.tolist()
    }
    with open(output_path, 'w') as f:
        json.dump(mesh_data, f, indent=4)

    print(f"\nMesh saved successfully to {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a 2D channel mesh.")
    parser.add_argument('--output_path', type=str, default='channel_mesh.json',
                        help='Path to save the output JSON mesh file.')
    args = parser.parse_args()

    create_channel_mesh(output_path=args.output_path)
