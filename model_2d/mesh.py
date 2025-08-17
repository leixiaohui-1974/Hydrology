"""
Mesh Data Structures for the 2D Model
=====================================

This module defines the classes used to represent an unstructured
triangular mesh, including building the mesh topology from points and faces.
"""
import numpy as np
from collections import defaultdict

class Node:
    """Represents a vertex in the mesh."""
    def __init__(self, index, x, y):
        self.id = index
        self.x = x
        self.y = y

class Edge:
    """Represents an edge connecting two nodes."""
    def __init__(self, index, n1, n2):
        self.id = index
        self.nodes = (n1, n2)
        self.length = np.sqrt((n1.x - n2.x)**2 + (n1.y - n2.y)**2)
        # Normal vector (points from face1 to face2, or outward for boundary)
        self.normal = np.array([n2.y - n1.y, n1.x - n2.x]) / self.length
        self.face1 = None # The face on the "left" of the edge
        self.face2 = None # The face on the "right" of the edge

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
        self.z_bed = 0.0 # Bed elevation

class Mesh:
    """Container for the entire unstructured mesh and its topology."""
    def __init__(self):
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.faces: list[Face] = []
        self.boundary_edges: list[Edge] = []

    def build_from_points_and_triangles(self, points, triangles):
        """
        Builds the full mesh topology from a list of points and triangles.

        Args:
            points (list of tuples): e.g., [(x1, y1), (x2, y2), ...]
            triangles (list of tuples): e.g., [(0, 1, 2), (1, 3, 2), ...]
                                        referencing indices in the points list.
        """
        # 1. Create Node objects
        for i, (x, y) in enumerate(points):
            self.nodes.append(Node(i, x, y))

        # 2. Create Face objects
        for i, tri_indices in enumerate(triangles):
            n1, n2, n3 = [self.nodes[idx] for idx in tri_indices]
            self.faces.append(Face(i, n1, n2, n3))

        # 3. Build Edge topology
        edge_map = {} # Use a map to find shared edges
        edge_counter = 0

        for face_idx, face in enumerate(self.faces):
            node_indices = [n.id for n in face.nodes]
            # Define edges for the face in a consistent order (e.g., sorted indices)
            face_edges_indices = [
                tuple(sorted((node_indices[0], node_indices[1]))),
                tuple(sorted((node_indices[1], node_indices[2]))),
                tuple(sorted((node_indices[2], node_indices[0])))
            ]

            for edge_key in face_edges_indices:
                if edge_key not in edge_map:
                    # This is a new edge
                    n1, n2 = [self.nodes[idx] for idx in edge_key]
                    edge = Edge(edge_counter, n1, n2)
                    edge.face1 = face
                    edge_map[edge_key] = edge
                    self.edges.append(edge)
                    face.edges.append(edge)
                    edge_counter += 1
                else:
                    # This is a shared edge, seen for the second time
                    edge = edge_map[edge_key]
                    edge.face2 = face
                    face.edges.append(edge)

        # 4. Identify boundary edges
        for edge in self.edges:
            if edge.face2 is None:
                self.boundary_edges.append(edge)

        print(f"Mesh built successfully: {len(self.nodes)} nodes, {len(self.faces)} faces, {len(self.edges)} edges.")
