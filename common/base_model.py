"""
Common Base Classes for Coupled Modeling (Semi-Implicit)
========================================================

This module provides the abstract base classes for components designed
to work with the semi-implicit, simultaneous solver.
"""
from abc import ABC, abstractmethod

class BaseModelComponent(ABC):
    """
    Abstract base class for all components in a coupled water model.
    """
    def __init__(self, name: str):
        """
        Initializes the component with a unique name.
        """
        self.name = name
        self.outflow = 0.0

    @abstractmethod
    def get_num_vars(self) -> int:
        """
        Returns the number of state variables this component contributes
        to the global system.
        """
        pass

    @abstractmethod
    def get_matrix_contributions(self, controller) -> tuple:
        """
        Get the component's contributions to the global system matrix.

        Returns:
            A tuple (matrix_coeffs, rhs_coeffs), where:
            - matrix_coeffs is a list of (row_idx, col_idx, value) tuples.
            - rhs_coeffs is a list of (row_idx, value) tuples.
        """
        pass

    @abstractmethod
    def update_state(self, dX_slice):
        """
        Updates the component's internal state with its portion of the
        global solution vector.
        """
        pass

    def get_outflow(self) -> float:
        """
        Returns the primary outflow from the component after the last step.
        """
        return self.outflow
