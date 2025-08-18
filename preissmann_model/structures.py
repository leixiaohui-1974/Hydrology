"""
Hydraulic Structures Module
===========================

This module defines the classes for hydraulic structures like gates and pumps
that can be placed within a river reach.
"""
from abc import ABC, abstractmethod
import numpy as np

class HydraulicStructure(ABC):
    """
    Abstract base class for all hydraulic structures.
    """
    def __init__(self, name: str, node_index: int):
        """
        Initializes the structure.

        Args:
            name (str): The unique name of the structure.
            node_index (int): The index of the node in the river reach where
                              the structure is located.
        """
        self.name = name
        self.node_index = node_index

    @abstractmethod
    def get_equation_rows(self, Q_up: float, Z_up: float, Q_down: float, Z_down: float) -> tuple:
        """
        Calculates the linearized equation rows for this structure.
        A structure typically provides one or two equations to replace the
        standard continuity/momentum equations at its node.

        For a structure at node `i`, this equation relates the variables at
        node `i-1`, `i`, and `i+1`.

        Returns:
            A tuple containing the matrix row(s) and RHS value(s) for the
            global system matrix. The exact format will depend on how it's
            integrated into the main model's matrix assembly.
        """
        pass


class Gate(HydraulicStructure):
    """
    Represents a gate structure (e.g., sluice gate).

    The hydraulic behavior is typically governed by an orifice or weir equation.
    Q = C * A * sqrt(2g * delta_H)
    """
    def __init__(self, name: str, node_index: int, opening_height: float, width: float, C_d: float = 0.6):
        super().__init__(name, node_index)
        self.opening_height = opening_height
        self.width = width
        self.C_d = C_d # Discharge coefficient

    def get_linearized_equation(self, Z_up: float, Z_down: float, Q_at_gate: float, g: float = 9.81) -> tuple:
        """
        Returns the coefficients for the linearized orifice equation.
        Equation: Q = C_d * A * sqrt(2*g*(Z_up - Z_down))
        Linearized form: C1*dZ_up + C2*dZ_down + C3*dQ_at_gate = RHS

        Args:
            Z_up (float): Water level at the upstream node.
            Z_down (float): Water level at the downstream node (the gate's node).
            Q_at_gate (float): Discharge at the gate's node.
            g (float): Acceleration due to gravity.

        Returns:
            A tuple (coeffs, rhs), where coeffs is a dictionary of coefficients
            for dZ_up, dZ_down, dQ_at_gate, and rhs is the right-hand side value.
        """
        head_diff = Z_up - Z_down
        if head_diff <= 1e-6: # Avoid division by zero or sqrt of negative
            # If no head diff, gate is closed or water is level.
            # Equation becomes Q = 0, or linearized: 1*dQ = -Q
            return ({'dQ': 1.0}, -Q_at_gate)

        Ag = self.width * self.opening_height
        C = self.C_d * Ag * np.sqrt(2 * g)

        # Coefficient for linearization
        coeff = (C / 2.0) / np.sqrt(head_diff)

        # Partial derivatives of F(Z_up, Z_down, Q) = Q - C*sqrt(Z_up - Z_down)
        c_dZ_up = -coeff
        c_dZ_down = coeff
        c_dQ = 1.0

        # RHS is -F(Q^n, Z^n)
        rhs = - (Q_at_gate - C * np.sqrt(head_diff))

        coeffs = {
            'dZ_up': c_dZ_up,
            'dZ_down': c_dZ_down,
            'dQ': c_dQ
        }

        return coeffs, rhs

    def get_equation_rows(self, Q_up: float, Z_up: float, Q_down: float, Z_down: float) -> tuple:
        # This method is now a placeholder for a more generic interface
        # if different structures needed different inputs.
        # For now, it calls the more specific linearized equation method.
        return self.get_linearized_equation(Z_up, Z_down, Q_down)


class Pump(HydraulicStructure):
    """
    Represents a pump.

    The hydraulic behavior is governed by the pump's characteristic curve,
    which defines the head added for a given discharge.
    delta_H = a*Q^2 + b*Q + c
    """
    def __init__(self, name: str, node_index: int, curve_coeffs: tuple):
        super().__init__(name, node_index)
        self.curve_coeffs = curve_coeffs # (a, b, c)

    def get_linearized_equation(self, Z_up: float, Z_down: float, Q_at_pump: float) -> tuple:
        """
        Returns the coefficients for the linearized pump characteristic curve.
        Eq: Z_down - Z_up = a*Q^2 + b*Q + c
        Linearized: C1*dZ_up + C2*dZ_down + C3*dQ_at_pump = RHS
        """
        a, b, c = self.curve_coeffs

        # Partial derivatives of F(...) = Z_down - Z_up - (aQ^2 + bQ + c)
        c_dZ_up = -1.0
        c_dZ_down = 1.0
        c_dQ = -2 * a * Q_at_pump - b

        # RHS is -F(Q^n, Z^n)
        rhs = -( (Z_down - Z_up) - (a * Q_at_pump**2 + b * Q_at_pump + c) )

        coeffs = {
            'dZ_up': c_dZ_up,
            'dZ_down': c_dZ_down,
            'dQ': c_dQ
        }

        return coeffs, rhs

    def get_equation_rows(self, Q_up: float, Z_up: float, Q_down: float, Z_down: float) -> tuple:
        # For a pump at node i, Q_down is Q_i, Z_down is Z_i, Z_up is Z_{i-1}
        return self.get_linearized_equation(Z_up, Z_down, Q_down)


class LateralLink(HydraulicStructure):
    """
    A special structure that models bi-directional flow over a weir
    connecting this (1D) model to a 2D model cell.
    """
    def __init__(self, name: str, node_index: int, model_2d, face_2d_idx: int,
                 crest_elevation: float, width: float, weir_coeff: float = 1.6):
        super().__init__(name, node_index)
        self.model_2d = model_2d
        self.face_2d_idx = face_2d_idx
        self.crest_elevation = crest_elevation
        self.width = width
        self.weir_coeff = weir_coeff

    def get_coupling_equation(self):
        """
        Calculates the linearized weir equation for the link.
        This is not a standard equation row but provides the coefficients
        to modify the continuity equations of the linked components.
        """
        # 1. Get current state from connected components
        Z_1d = self.model_1d.Z[self.node_1d_idx] # This needs a reference to the parent 1D model
        face_2d = self.model_2d.mesh.faces[self.face_2d_idx]
        Z_2d = face_2d.z_bed + face_2d.h

        # 2. Calculate linearized weir flow: Q_exchange = Q_n + dQ_dZ1d*dZ_1d + dQ_dZ2d*dh_2d
        Q_n = 0.0
        dQ_dZ1d = 0.0
        dQ_dh2d = 0.0

        head_1d = Z_1d - self.crest_elevation
        head_2d = Z_2d - self.crest_elevation

        if Z_1d > Z_2d and head_1d > 0:
            Q_n = self.weir_coeff * self.width * head_1d**1.5
            dQ_dZ1d = 1.5 * self.weir_coeff * self.width * np.sqrt(head_1d)
        elif Z_2d > Z_1d and head_2d > 0:
            Q_n = -self.weir_coeff * self.width * head_2d**1.5
            dQ_dh2d = -1.5 * self.weir_coeff * self.width * np.sqrt(head_2d)

        return Q_n, dQ_dZ1d, dQ_dh2d

    def get_equation_rows(self, Q_up: float, Z_up: float, Q_down: float, Z_down: float) -> tuple:
        # This structure doesn't return a standard equation row,
        # it's a special case handled by the HydraulicModel's matrix assembly.
        return None, None # Placeholder
