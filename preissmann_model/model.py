"""
Main Hydraulic Model Module
===========================

This module contains the main HydraulicModel class that orchestrates the
1D hydraulic simulation using the Preissmann scheme.
"""

import numpy as np
from .reach import RiverReach
from common.base_model import BaseModelComponent

class HydraulicModel(BaseModelComponent):
    """
    Main class for the 1D hydraulic model.
    This component represents a river reach.
    """
    def __init__(self, name: str, reach: RiverReach, dt: float, downstream_level: float, theta: float = 1.0, g: float = 9.81):
        super().__init__(name)
        self.reach = reach
        self.dt = dt
        self.theta = theta
        self.g = g

        # Boundary condition setting
        self.downstream_level = downstream_level

        # Initialize state variables
        self.num_nodes = self.reach.num_sections
        self.Q = np.zeros(self.num_nodes)
        self.Z = np.zeros(self.num_nodes)

        # Bed elevation (assuming constant slope)
        self.Z_bed = np.zeros(self.num_nodes)
        cumulative_length = 0
        for i in range(self.num_nodes - 2, -1, -1):
            cumulative_length += self.reach.lengths[i]
            self.Z_bed[i] = self.Z_bed[i+1] + self.reach.slope * self.reach.lengths[i]

    def _build_system_matrices(self):
        # This function remains largely the same as before.
        n = self.num_nodes
        g = self.g
        dt = self.dt
        theta = self.theta
        AA, BB, DD = [], [], []
        for i in range(n - 1):
            dx = self.reach.lengths[i]
            Z_i, Q_i = self.Z[i], self.Q[i]
            Z_i1, Q_i1 = self.Z[i+1], self.Q[i+1]
            y_i = Z_i - self.Z_bed[i]
            y_i1 = Z_i1 - self.Z_bed[i+1]
            cs_i = self.reach.cross_sections[i]
            area_i = cs_i.area(y_i)
            T_i = cs_i.top_width(y_i)
            Rh_i = cs_i.hydraulic_radius(y_i)
            cs_i1 = self.reach.cross_sections[i+1]
            area_i1 = cs_i1.area(y_i1)
            T_i1 = cs_i1.top_width(y_i1)
            Rh_i1 = cs_i1.hydraulic_radius(y_i1)
            Q = 0.5 * (Q_i + Q_i1)
            A = 0.5 * (area_i + area_i1)
            T = 0.5 * (T_i + T_i1)
            Rh = 0.5 * (Rh_i + Rh_i1)
            if A < 1e-6:
                AA.append(np.identity(2)); BB.append(-np.identity(2)); DD.append(np.zeros(2))
                continue
            psi = 0.5
            L1_c = psi * T / dt
            L2_c = (1-psi) * T / dt
            L3_c = -theta / dx
            L4_c = theta / dx
            RHS_c = -(Q_i1 - Q_i)/dx
            if A < 1e-6 or Rh < 1e-6:
                Sf = 0; d_Sf_dQ = 0
            else:
                Sf = (self.reach.manning_n**2 * Q * abs(Q)) / (A**2 * Rh**(4/3))
                d_Sf_dQ = (2 * self.reach.manning_n**2 * abs(Q)) / (A**2 * Rh**(4/3))
            L1_m = -g * A * theta / dx
            L2_m = g * A * theta / dx
            fric_term_Q = g * A * theta * d_Sf_dQ
            L3_m = (1-psi)/dt + fric_term_Q
            L4_m = psi/dt + fric_term_Q
            RHS_m = -g*A*((Z_i1 - Z_i)/dx - self.reach.slope) - g*A*Sf
            aa_i = np.array([[L1_c, L3_c], [L1_m, L3_m]])
            bb_i = np.array([[L2_c, L4_c], [L2_m, L4_m]])
            dd_i = np.array([RHS_c, RHS_m])
            AA.append(aa_i); BB.append(bb_i); DD.append(dd_i)
        return AA, BB, DD

    def step(self, inflows: dict, dt: float):
        """
        Performs a single time step of the simulation, conforming to the BaseModelComponent interface.
        """
        # Sum inflows from all upstream components
        Q_inflow = sum(inflows.values()) if inflows else 0.0

        n_vars = self.num_nodes * 2
        AA, BB, DD = self._build_system_matrices()
        M = np.zeros((n_vars, n_vars))
        R = np.zeros(n_vars)

        for i in range(self.num_nodes - 1):
            row = i * 2
            M[row:row+2, 2*i:2*i+2] = AA[i]
            M[row:row+2, 2*(i+1):2*(i+1)+2] = BB[i]
            R[row:row+2] = DD[i]

        # Upstream BC: Q_0 = Q_inflow
        M[n_vars-2, 1] = 1.0
        R[n_vars-2] = Q_inflow - self.Q[0]

        # Downstream BC: Z_{N-1} = self.downstream_level
        M[n_vars-1, n_vars-2] = 1.0
        R[n_vars-1] = self.downstream_level - self.Z[self.num_nodes-1]

        try:
            dX_flat = np.linalg.solve(M, R)
        except np.linalg.LinAlgError:
            print(f"Warning: Singular matrix in component '{self.name}'. Simulation may be unstable.")
            return

        relaxation_factor = 0.75
        for i in range(self.num_nodes):
            self.Z[i] += relaxation_factor * dX_flat[i*2]
            self.Q[i] += relaxation_factor * dX_flat[i*2 + 1]

        # Update the component's outflow state
        self.outflow = self.Q[-1]

    def run(self, num_steps: int, Q_inflow_hydrograph: list, Z_downstream_hydrograph: list):
        """
        Original run method for standalone execution.
        Note: This will be superseded by the global SimulationController.
        """
        if len(Q_inflow_hydrograph) < num_steps or len(Z_downstream_hydrograph) < num_steps:
            raise ValueError("Boundary condition hydrographs must be at least as long as num_steps.")

        print(f"--- Running standalone simulation for component '{self.name}' ---")
        for i in range(num_steps):
            # For standalone run, we manually create the inflows dict
            inflows = {'upstream': Q_inflow_hydrograph[i]}
            self.downstream_level = Z_downstream_hydrograph[i]
            self.step(inflows, self.dt)
        print("--- Standalone simulation finished ---")
