"""
Common Base Classes for Coupled Modeling
========================================

This module provides the abstract base classes that define a common
interface for all model components, allowing them to be connected
in a network.
"""
from abc import ABC, abstractmethod

class BaseModelComponent(ABC):
    """
    Abstract base class for all components in a coupled water model.

    Each component represents a part of the water system, such as a
    catchment, a river reach, a junction, or a structure.
    """
    def __init__(self, name: str):
        """
        Initializes the component with a unique name.

        Args:
            name (str): The unique identifier for this component.
        """
        self.name = name
        self.outflow = 0.0  # Default initial outflow

    @abstractmethod
    def step(self, inflows: dict, dt: float):
        """
        Execute the component's model for a single time step.

        This method should calculate the component's state at the end of
        the time step and update its internal state, including the `outflow`
        attribute.

        Args:
            inflows (dict): A dictionary where keys are the names of upstream
                            components (or user-defined inflow points) and
                            values are their outflows.
            dt (float): The time step duration in seconds.
        """
        pass

    def get_outflow(self) -> float:
        """
        Returns the primary outflow from the component after the last step.
        This is typically the value used by downstream components.
        """
        return self.outflow
