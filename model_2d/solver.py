"""
Finite Volume Solver for the 2D Shallow Water Equations
=======================================================

This module contains the core numerical solver.
"""
import numpy as np
from .mesh import Mesh

def finite_volume_step(mesh: Mesh, dt: float, g: float = 9.81):
    """
    Performs one time step of the Finite Volume solver using a Rusanov flux.
    This is a first-order accurate scheme.
    """

    # --- 1. Calculate fluxes for all edges ---
    edge_fluxes = np.zeros((len(mesh.edges), 3)) # Store [F_h, F_uh, F_vh] for each edge

    for i, edge in enumerate(mesh.edges):
        # --- a. Get left and right states ---
        face_l = edge.face1
        U_l = np.array([face_l.h, face_l.uh, face_l.vh])

        # For boundary edges, construct a "ghost" cell state based on the BC type
        if edge.face2 is None:
            # --- Wall Boundary (Reflective) ---
            if edge.boundary_type == 'wall':
                h_l_b, uh_l_b, vh_l_b = U_l[0], U_l[1], U_l[2]
                h_r = h_l_b
                u_l_b = uh_l_b / h_l_b if h_l_b > 1e-6 else 0
                v_l_b = vh_l_b / h_l_b if h_l_b > 1e-6 else 0
                un_l = u_l_b * edge.normal[0] + v_l_b * edge.normal[1]
                u_r_reflected = u_l_b - 2 * un_l * edge.normal[0]
                v_r_reflected = v_l_b - 2 * un_l * edge.normal[1]
                uh_r = h_r * u_r_reflected
                vh_r = h_r * v_r_reflected
                U_r = np.array([h_r, uh_r, vh_r])

            # --- Flow Boundary (Inflow/Outflow) ---
            elif edge.boundary_type == 'flow':
                # The desired flow Q is stored on the edge object by the model
                Q_boundary = getattr(edge, 'flow_rate', 0.0)
                h_l_b = U_l[0]

                # Assume water depth of ghost cell is same as internal cell
                h_r = h_l_b

                # Calculate required normal velocity to achieve the desired flow Q
                # Q = u_n * h * L  => u_n = Q / (h * L)
                u_n_req = Q_boundary / (h_l_b * edge.length) if h_l_b * edge.length > 1e-6 else 0

                # We assume the tangential velocity is zero for the ghost cell
                # So, the ghost velocity vector is purely in the normal direction
                u_r = u_n_req * edge.normal[0]
                v_r = u_n_req * edge.normal[1]

                uh_r = h_r * u_r
                vh_r = h_r * v_r
                U_r = np.array([h_r, uh_r, vh_r])

            else: # Default to wall if type is unknown
                U_r = U_l

        else: # Internal edge
            face_r = edge.face2
            U_r = np.array([face_r.h, face_r.uh, face_r.vh])

        # --- b. Calculate velocities and wave speeds ---
        h_l, uh_l, vh_l = U_l
        h_r, uh_r, vh_r = U_r

        u_l = uh_l / h_l if h_l > 1e-6 else 0
        v_l = vh_l / h_l if h_l > 1e-6 else 0
        u_r = uh_r / h_r if h_r > 1e-6 else 0
        v_r = vh_r / h_r if h_r > 1e-6 else 0

        # Wave speed calculation
        s_l = np.sqrt(u_l**2 + v_l**2) + np.sqrt(g * h_l)
        s_r = np.sqrt(u_r**2 + v_r**2) + np.sqrt(g * h_r)
        s_max = max(s_l, s_r)

        # --- c. Calculate fluxes normal to the edge ---
        # F = [hu, hu^2/h + gh^2/2, huv/h]
        # G = [hv, huv/h, hv^2/h + gh^2/2]
        # Flux term F_n = F*nx + G*ny

        F_l_n = uh_l * edge.normal[0] + vh_l * edge.normal[1]
        F_r_n = uh_r * edge.normal[0] + vh_r * edge.normal[1]

        # Momentum flux terms
        p_l = 0.5 * g * h_l**2
        p_r = 0.5 * g * h_r**2

        F_uh_n = (uh_l**2/h_l + p_l if h_l > 1e-6 else 0) * edge.normal[0] + (uh_l*v_l/h_l if h_l > 1e-6 else 0) * edge.normal[1]
        F_ur_n = (uh_r**2/h_r + p_r if h_r > 1e-6 else 0) * edge.normal[0] + (uh_r*v_r/h_r if h_r > 1e-6 else 0) * edge.normal[1]

        F_vh_n = (uh_l*v_l/h_l if h_l > 1e-6 else 0) * edge.normal[0] + (vh_l**2/h_l + p_l if h_l > 1e-6 else 0) * edge.normal[1]
        F_vr_n = (uh_r*v_r/h_r if h_r > 1e-6 else 0) * edge.normal[0] + (vh_r**2/h_r + p_r if h_r > 1e-6 else 0) * edge.normal[1]

        Flux_l = np.array([F_l_n, F_uh_n, F_vh_n])
        Flux_r = np.array([F_r_n, F_ur_n, F_vr_n])

        # --- d. Calculate Rusanov flux ---
        rusanov_flux = 0.5 * (Flux_l + Flux_r) - 0.5 * s_max * (U_r - U_l)
        edge_fluxes[i, :] = rusanov_flux

    # --- 2. Update cell states using fluxes ---
    face_updates = np.zeros((len(mesh.faces), 3))

    for i, edge in enumerate(mesh.edges):
        flux = edge_fluxes[i] * edge.length

        # Add flux to the "left" face (face1)
        face_updates[edge.face1.id, :] -= flux

        # Subtract flux from the "right" face (face2), if it exists
        if edge.face2 is not None:
            face_updates[edge.face2.id, :] += flux

    # Apply the updates to each face
    for i, face in enumerate(mesh.faces):
        update = face_updates[i] * (dt / face.area)
        face.h += update[0]
        face.uh += update[1]
        face.vh += update[2]

    return mesh
