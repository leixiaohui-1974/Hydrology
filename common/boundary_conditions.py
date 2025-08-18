"""
Boundary Conditions Module
==========================

This module defines classes for representing different types of boundary conditions.
"""
from abc import ABC, abstractmethod
from typing import Callable

class BoundaryCondition(ABC):
    """Abstract base class for boundary conditions."""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_value(self, time: float) -> float:
        """Returns the value of the boundary condition at a given time."""
        pass

class InflowBC(BoundaryCondition):
    """Represents a time-varying inflow (discharge) boundary condition."""
    def __init__(self, name: str, discharge_func: Callable[[float], float]):
        super().__init__(name)
        self.discharge_func = discharge_func

    def get_value(self, time: float) -> float:
        return self.discharge_func(time)

class WaterLevelBC(BoundaryCondition):
    """Represents a time-varying water level boundary condition."""
    def __init__(self, name: str, level_func: Callable[[float], float]):
        super().__init__(name)
        self.level_func = level_func

    def get_value(self, time: float) -> float:
        return self.level_func(time)
