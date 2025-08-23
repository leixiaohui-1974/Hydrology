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
    This version includes bed slope source terms.
    """
    # Store initial water depth for source term calculation, handle small values
    h_initial = np.maximum(1e-6, np.array([f.h for f in mesh.faces]))

    # --- 1. Calculate fluxes for all edges ---
    edge_fluxes = np.zeros((len(mesh.edges), 3))

    for i, edge in enumerate(mesh.edges):
        # --- a. Get left and right states ---
        face_l = edge.face1
        h_l, uh_l, vh_l = face_l.h, face_l.uh, face_l.vh
        U_l = np.array([h_l, uh_l, vh_l])

        if edge.face2 is None: # Boundary edge
            if edge.boundary_type == 'wall':
                h_r = h_l
                u_l_b = uh_l / h_l if h_l > 1e-6 else 0
                v_l_b = vh_l / h_l if h_l > 1e-6 else 0
                un_l = u_l_b * edge.normal[0] + v_l_b * edge.normal[1]
                u_r_reflected = u_l_b - 2 * un_l * edge.normal[0]
                v_r_reflected = v_l_b - 2 * un_l * edge.normal[1]
                uh_r = h_r * u_r_reflected
                vh_r = h_r * v_r_reflected
                U_r = np.array([h_r, uh_r, vh_r])
            elif edge.boundary_type == 'flow':
                Q_boundary = getattr(edge, 'flow_rate', 0.0)
                h_r = h_l
                u_n_req = Q_boundary / (h_l * edge.length) if h_l * edge.length > 1e-6 else 0
                u_r = u_n_req * edge.normal[0]
                v_r = u_n_req * edge.normal[1]
                uh_r = h_r * u_r
                vh_r = h_r * v_r
                U_r = np.array([h_r, uh_r, vh_r])
            else:
                U_r = U_l
        else: # Internal edge
            face_r = edge.face2
            U_r = np.array([face_r.h, face_r.uh, face_r.vh])

        # --- b. Calculate velocities and wave speeds ---
        h_r, uh_r, vh_r = U_r
        u_l = uh_l / h_l if h_l > 1e-6 else 0
        v_l = vh_l / h_l if h_l > 1e-6 else 0
        u_r = uh_r / h_r if h_r > 1e-6 else 0
        v_r = vh_r / h_r if h_r > 1e-6 else 0

        s_l = np.sqrt(u_l**2 + v_l**2) + np.sqrt(g * h_l)
        s_r = np.sqrt(u_r**2 + v_r**2) + np.sqrt(g * h_r)
        s_max = max(s_l, s_r)

        # --- c. Calculate fluxes normal to the edge ---
        p_l = 0.5 * g * h_l**2
        p_r = 0.5 * g * h_r**2
        F_l_n = uh_l * edge.normal[0] + vh_l * edge.normal[1]
        F_r_n = uh_r * edge.normal[0] + vh_r * edge.normal[1]
        F_uh_n = (uh_l**2/h_l + p_l if h_l > 1e-6 else 0) * edge.normal[0] + (uh_l*v_l/h_l if h_l > 1e-6 else 0) * edge.normal[1]
        F_ur_n = (uh_r**2/h_r + p_r if h_r > 1e-6 else 0) * edge.normal[0] + (uh_r*v_r/h_r if h_r > 1e-6 else 0) * edge.normal[1]
        F_vh_n = (uh_l*v_l/h_l if h_l > 1e-6 else 0) * edge.normal[0] + (vh_l**2/h_l + p_l if h_l > 1e-6 else 0) * edge.normal[1]
        F_vr_n = (uh_r*v_r/h_r if h_r > 1e-6 else 0) * edge.normal[0] + (vh_r**2/h_r + p_r if h_r > 1e-6 else 0) * edge.normal[1]
        Flux_l = np.array([F_l_n, F_uh_n, F_vh_n])
        Flux_r = np.array([F_r_n, F_ur_n, F_vr_n])

        # --- d. Calculate Rusanov flux ---
        rusanov_flux = 0.5 * (Flux_l + Flux_r) - 0.5 * s_max * (U_r - U_l)
        edge_fluxes[i, :] = rusanov_flux

    # --- 2. Sum fluxes for each cell ---
    face_updates = np.zeros((len(mesh.faces), 3))
    for i, edge in enumerate(mesh.edges):
        flux = edge_fluxes[i] * edge.length
        face_updates[edge.face1.id, :] -= flux
        if edge.face2 is not None:
            face_updates[edge.face2.id, :] += flux

    # --- 3. Calculate bed slope source term using a robust Green-Gauss method ---
    face_gradient_integrals = np.zeros((len(mesh.faces), 2)) # Stores ∫(z_b * n) dL

    for face in mesh.faces:
        for edge in face.edges:
            # a) Determine the value of z_bed at the edge center
            if edge.face2 is None: # Boundary edge
                z_edge = face.z_bed
            else: # Internal edge
                other_face = edge.face2 if edge.face1 == face else edge.face1
                z_edge = (face.z_bed + other_face.z_bed) / 2.0

            # b) Determine the outward-pointing normal for this specific face
            # Find the third node of the face that is not on the edge
            p3 = [n for n in face.nodes if n not in edge.nodes][0]
            # Vector from edge center to the third node's position
            vec_to_p3 = np.array([p3.x, p3.y]) - \
                        np.array([(edge.nodes[0].x + edge.nodes[1].x) / 2.0,
                                  (edge.nodes[0].y + edge.nodes[1].y) / 2.0])

            # The default edge normal is arbitrary. If its dot product with the
            # vector to the face's internal point (p3) is positive, it means
            # the normal is pointing inwards, so we must flip it.
            if np.dot(vec_to_p3, edge.normal) > 0:
                outward_normal = -edge.normal
            else:
                outward_normal = edge.normal

            # c) Add the contribution to the integral sum for the face
            face_gradient_integrals[face.id, :] += z_edge * outward_normal * edge.length

    # d) Divide by area to get the final gradient for each face
    face_areas = np.array([f.area for f in mesh.faces])
    face_areas[face_areas < 1e-9] = 1e-9
    bed_gradients = face_gradient_integrals / face_areas[:, np.newaxis]

    # e) Calculate the source term S = [0, -g*h*dz/dx, -g*h*dz/dy]
    source_terms = np.zeros((len(mesh.faces), 3))
    source_terms[:, 1] = -g * h_initial * bed_gradients[:, 0]
    source_terms[:, 2] = -g * h_initial * bed_gradients[:, 1]

    # Add source term contribution to the final update
    # The term is S * dt, so we multiply by Area here to cancel the later division
    face_updates += source_terms * face_areas[:, np.newaxis]

    # --- 4. Apply the final updates to each face ---
    for i, face in enumerate(mesh.faces):
        update = face_updates[i] * (dt / face.area)

        # Update conserved variables, ensuring positivity for h
        face.h = max(1e-6, face.h + update[0])
        face.uh += update[1]
        face.vh += update[2]

    return mesh
