"""
Mesh Data Structures for the 2D Model
=====================================

This module defines the classes used to represent an unstructured
triangular mesh, including building the mesh topology from points and faces.
"""
import numpy as np
from collections import defaultdict
import rasterio

class Node:
    """Represents a vertex in the mesh."""
    def __init__(self, index, x, y, z=0.0):
        self.id = index
        self.x = x
        self.y = y
        self.z = z # Bed elevation at the node

class Edge:
    """Represents an edge connecting two nodes."""
    def __init__(self, index, n1, n2):
        self.id = index
        self.nodes = (n1, n2)
        self.length = np.sqrt((n1.x - n2.x)**2 + (n1.y - n2.y)**2)
        # Normal vector (points from face1 to face2, or outward for boundary).
        # Using the standard counter-clockwise rotation: (x, y) -> (-y, x)
        self.normal = np.array([-(n2.y - n1.y), n2.x - n1.x]) / self.length
        self.face1 = None # The face on the "left" of the edge
        self.face2 = None # The face on the "right" of the edge
        self.boundary_type = None # e.g., 'wall', 'inflow', 'outflow'

class Face:
    """Represents a triangular face (cell) in the mesh."""
    def __init__(self, index, n1, n2, n3):
        self.id = index
        self.nodes = (n1, n2, n3)
        self.edges = []
        # Calculate centroid and area
        self.centroid = np.array([(n1.x+n2.x+n3.x)/3.0, (n1.y+n2.y+n3.y)/3.0])
        self.area = 0.5 * abs(n1.x*(n2.y-n3.y) + n2.x*(n3.y-n1.y) + n3.x*(n1.y-n2.y))

        # State variables (conserved quantities)
        self.h = 0.0  # Water depth
        self.uh = 0.0 # x-momentum
        self.vh = 0.0 # y-momentum
        # Bed elevation is the average of the nodes' elevations
        self.z_bed = (n1.z + n2.z + n3.z) / 3.0

class Mesh:
    """Container for the entire unstructured mesh and its topology."""
    def __init__(self):
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.faces: list[Face] = []
        # Store boundary edges in a dictionary keyed by type
        self.boundary_edges: dict[str, list[Edge]] = defaultdict(list)

    def set_boundary_edge_type(self, edge_id: int, boundary_type: str):
        """Sets the boundary type for a specific boundary edge."""
        edge = self.edges[edge_id]
        if edge.face2 is not None:
            raise ValueError(f"Edge {edge_id} is not a boundary edge.")

        # Remove from the old list if it exists
        for b_type, edge_list in self.boundary_edges.items():
            if edge in edge_list:
                edge_list.remove(edge)
                break

        # Add to the new list
        edge.boundary_type = boundary_type
        self.boundary_edges[boundary_type].append(edge)
        print(f"Set boundary type for edge {edge_id} to '{boundary_type}'.")


    def build_from_points_and_triangles(self, points, triangles):
        """
        Builds the full mesh topology from a list of points and triangles.
        Points can be 2D (x, y) or 3D (x, y, z).
        """
        # 1. Create Node objects
        for i, p in enumerate(points):
            if len(p) == 3:
                self.nodes.append(Node(i, p[0], p[1], p[2]))
            else:
                self.nodes.append(Node(i, p[0], p[1]))

        # 2. Create Face objects
        for i, tri_indices in enumerate(triangles):
            n1, n2, n3 = [self.nodes[idx] for idx in tri_indices]
            self.faces.append(Face(i, n1, n2, n3))

        # 3. Build Edge topology
        edge_map = {}
        edge_counter = 0
        for face in self.faces:
            node_indices = [n.id for n in face.nodes]
            face_edges_indices = [
                tuple(sorted((node_indices[0], node_indices[1]))),
                tuple(sorted((node_indices[1], node_indices[2]))),
                tuple(sorted((node_indices[2], node_indices[0])))
            ]
            for edge_key in face_edges_indices:
                if edge_key not in edge_map:
                    n1, n2 = [self.nodes[idx] for idx in edge_key]
                    edge = Edge(edge_counter, n1, n2)
                    edge.face1 = face
                    edge_map[edge_key] = edge
                    self.edges.append(edge)
                    face.edges.append(edge)
                    edge_counter += 1
                else:
                    edge = edge_map[edge_key]
                    edge.face2 = face
                    face.edges.append(edge)

        # 4. Identify boundary edges and default them to 'wall' type
        for edge in self.edges:
            if edge.face2 is None:
                edge.boundary_type = 'wall'
                self.boundary_edges['wall'].append(edge)

        print(f"Mesh built successfully: {len(self.nodes)} nodes, {len(self.faces)} faces, {len(self.edges)} edges.")

    def set_bed_elevation_from_dem(self, dem_path: str):
        """
        Sets the z attribute for each node by sampling a DEM raster,
        then updates the z_bed for each face.

        Args:
            dem_path (str): The file path to the DEM raster (e.g., GeoTIFF).
        """
        print(f"Sampling node elevations from DEM: {dem_path}")
        try:
            with rasterio.open(dem_path) as dem:
                # 1. Collect all node coordinates
                coords = [(node.x, node.y) for node in self.nodes]

                # 2. Sample the raster at all node locations
                elevations = [val[0] for val in dem.sample(coords)]

                # 3. Assign the sampled elevations to the nodes
                for node, elev in zip(self.nodes, elevations):
                    node.z = float(elev)

                # 4. After updating node elevations, recalculate face elevations
                for face in self.faces:
                    face.z_bed = (face.nodes[0].z + face.nodes[1].z + face.nodes[2].z) / 3.0

                print(f"Successfully set node and face elevations for {len(self.nodes)} nodes.")

        except Exception as e:
            print(f"Error reading DEM or sampling elevations: {e}")
            raise
