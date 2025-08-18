import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from typing import List

class ImplicitSimulationController:
    """
    Manages and executes a network of model components using a semi-implicit,
    simultaneous solution scheme.
    """
    def __init__(self, components: List, dt: float):
        self.components = components
        self.dt = dt
        self.current_time = 0.0

        # Assign variable offsets to each component
        self.var_map = {}
        total_vars = 0
        for comp in self.components:
            num_vars = comp.get_num_vars()
            self.var_map[comp.name] = {
                "offset": total_vars,
                "num_vars": num_vars
            }
            total_vars += num_vars
        self.total_vars = total_vars

    def get_global_var_index(self, component, local_idx: int) -> int:
        """Calculates the global index for a component's local variable index."""
        return self.var_map[component.name]["offset"] + local_idx

    def run(self, num_steps: int):
        """Runs the full simulation."""
        print("--- Initializing Implicit Simulation Controller ---")

        for t in range(num_steps):
            self.current_time = t * self.dt
            print(f"--- Controller: Time step {t+1}/{num_steps} (t={self.current_time:.2f}s) ---")

            # 1. Assemble the global matrix M and vector R
            # Using a List of Lists (LIL) format for easy coefficient insertion
            M = sp.lil_matrix((self.total_vars, self.total_vars))
            R = np.zeros(self.total_vars)

            for comp in self.components:
                # The explicit 2D model runs its step inside this call
                if comp.name == "Floodplain":
                    # Pass inflows from links to the explicit model
                    link_inflows = {}
                    for link in self.components:
                        if hasattr(link, 'model_2d') and link.model_2d == comp:
                             # This is a simplification; assumes link Q is from previous step
                             link_inflows[link.link_2d_face_idx] = link.Q
                    comp.inflows = link_inflows

                matrix_coeffs, rhs_coeffs = comp.get_matrix_contributions(self)

                for r, c, v in matrix_coeffs:
                    M[r, c] += v
                for r, v in rhs_coeffs:
                    R[r] += v

            # 2. Solve the linear system M * dX = R
            try:
                # Convert M to a more efficient format for solving
                M_csr = M.tocsr()
                dX = spla.spsolve(M_csr, R)
            except Exception as e:
                print(f"FATAL: Linear solve failed at step {t+1}. Error: {e}")
                print("Matrix M:\n", M.toarray())
                print("Vector R:\n", R)
                return

            # 3. Update the state of each component
            for comp in self.components:
                offset = self.var_map[comp.name]["offset"]
                num_vars = self.var_map[comp.name]["num_vars"]
                if num_vars > 0:
                    dX_slice = dX[offset : offset + num_vars]
                    comp.update_state(dX_slice)

            yield {"step": t + 1, "num_steps": num_steps}

        print("--- Simulation Finished ---")

    def get_results(self):
        """Gathers results from all components."""
        all_results = {}
        for comp in self.components:
            if hasattr(comp, 'get_results'):
                all_results[comp.name] = comp.get_results()
        return all_results
