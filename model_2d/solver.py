"""
Finite Volume Solver for the 2D Shallow Water Equations
=======================================================

This module contains the core numerical solver, rewritten for clarity and correctness.
"""
import numpy as np
from .mesh import Mesh

def finite_volume_step(mesh: Mesh, dt: float, g: float = 9.81):
    """
    Performs one time step of a first-order finite volume scheme with a
    Rusanov flux and bed slope source terms.
    """
    num_faces = len(mesh.faces)
    num_edges = len(mesh.edges)

    # --- 1. Vectorize state variables from mesh objects ---
    h = np.array([f.h for f in mesh.faces])
    uh = np.array([f.uh for f in mesh.faces])
    vh = np.array([f.vh for f in mesh.faces])
    z_bed = np.array([f.z_bed for f in mesh.faces])
    areas = np.array([f.area for f in mesh.faces])

    # Avoid division by zero for dry cells
    h_inv = np.zeros_like(h)
    wet_cells = h > 1e-6
    h_inv[wet_cells] = 1.0 / h[wet_cells]

    u = uh * h_inv
    v = vh * h_inv

    # --- 2. Calculate Bed Slope Source Term (Direct Gradient on Triangle) ---
    bed_gradients = np.zeros((num_faces, 2))
    for i, face in enumerate(mesh.faces):
        n1, n2, n3 = face.nodes[0], face.nodes[1], face.nodes[2]

        # Using the formula for the gradient of a linear function over a triangle
        # See: https://en.wikipedia.org/wiki/Finite_volume_method_for_unstructured_mesh
        dz_dx = (n1.z * (n2.y - n3.y) + n2.z * (n3.y - n1.y) + n3.z * (n1.y - n2.y)) / (2 * face.area)
        dz_dy = (n1.z * (n3.x - n2.x) + n2.z * (n1.x - n3.x) + n3.z * (n2.x - n1.x)) / (2 * face.area)

        bed_gradients[i, 0] = dz_dx
        bed_gradients[i, 1] = dz_dy

    safe_areas = np.maximum(1e-9, areas)

    source_terms = np.zeros((num_faces, 3))
    source_terms[:, 1] = -g * h * bed_gradients[:, 0]
    source_terms[:, 2] = -g * h * bed_gradients[:, 1]

    # --- 3. Calculate Fluxes Across All Edges ---
    edge_fluxes = np.zeros((num_edges, 3))

    for i, edge in enumerate(mesh.edges):
        # Get left state (always face1)
        f1_idx = edge.face1.id
        U_l = np.array([h[f1_idx], uh[f1_idx], vh[f1_idx]])
        u_l, v_l = u[f1_idx], v[f1_idx]

        # Get right state (face2 or ghost cell)
        if edge.face2 is not None: # Internal edge
            f2_idx = edge.face2.id
            U_r = np.array([h[f2_idx], uh[f2_idx], vh[f2_idx]])
            u_r, v_r = u[f2_idx], v[f2_idx]
        else: # Boundary edge
            h_l = U_l[0]
            if edge.boundary_type == 'wall':
                h_r = h_l
                un_l = u_l * edge.normal[0] + v_l * edge.normal[1]
                u_r = u_l - 2 * un_l * edge.normal[0]
                v_r = v_l - 2 * un_l * edge.normal[1]
            else: # Default to transmissive/open boundary
                h_r, u_r, v_r = h_l, u_l, v_l

            U_r = np.array([h_r, h_r * u_r, h_r * v_r])

        # Calculate wave speeds
        s_l = np.sqrt(u_l**2 + v_l**2) + np.sqrt(g * U_l[0])
        s_r = np.sqrt(u_r**2 + v_r**2) + np.sqrt(g * U_r[0])
        s_max = max(s_l, s_r)

        # Calculate fluxes (F_n = F*nx + G*ny)
        p_l = 0.5 * g * U_l[0]**2
        p_r = 0.5 * g * U_r[0]**2

        flux_l = np.array([
            U_l[1]*edge.normal[0] + U_l[2]*edge.normal[1],
            (u_l*U_l[1] + p_l)*edge.normal[0] + (u_l*U_l[2])*edge.normal[1],
            (v_l*U_l[1])*edge.normal[0] + (v_l*U_l[2] + p_l)*edge.normal[1]
        ])
        flux_r = np.array([
            U_r[1]*edge.normal[0] + U_r[2]*edge.normal[1],
            (u_r*U_r[1] + p_r)*edge.normal[0] + (u_r*U_r[2])*edge.normal[1],
            (v_r*U_r[1])*edge.normal[0] + (v_r*U_r[2] + p_r)*edge.normal[1]
        ])

        # Rusanov flux
        edge_fluxes[i, :] = 0.5 * (flux_l + flux_r) - 0.5 * s_max * (U_r - U_l)

    # --- 4. Aggregate Updates for Each Face ---
    face_updates = np.zeros((num_faces, 3))
    for i, edge in enumerate(mesh.edges):
        flux_contribution = edge_fluxes[i] * edge.length
        face_updates[edge.face1.id] -= flux_contribution
        if edge.face2 is not None:
            face_updates[edge.face2.id] += flux_contribution

    # --- 5. Combine Flux and Source Term Updates and Apply to State ---
    # Convert source term S (rate) to an update contribution S*Area
    total_update = (face_updates + source_terms * safe_areas[:, np.newaxis]) * (dt / safe_areas[:, np.newaxis])

    h_new = h + total_update[:, 0]
    uh_new = uh + total_update[:, 1]
    vh_new = vh + total_update[:, 2]

    # Ensure positivity and write back to mesh objects
    for i, face in enumerate(mesh.faces):
        face.h = max(1e-6, h_new[i])
        if face.h < 1e-6:
            face.uh = 0.0
            face.vh = 0.0
        else:
            face.uh = uh_new[i]
            face.vh = vh_new[i]

    return mesh
