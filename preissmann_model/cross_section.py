"""
Cross-Section Module
====================

This module defines the classes and functions related to the geometry
of a river cross-section.
"""
from abc import ABC, abstractmethod

class BaseCrossSection(ABC):
    """Abstract base class for cross-sections."""

    @abstractmethod
    def area(self, y):
        """Calculate the wetted area for a given water depth y."""
        pass

    @abstractmethod
    def top_width(self, y):
        """Calculate the top width for a given water depth y."""
        pass

    @abstractmethod
    def wetted_perimeter(self, y):
        """Calculate the wetted perimeter for a given water depth y."""
        pass

    def hydraulic_radius(self, y):
        """Calculate the hydraulic radius."""
        area = self.area(y)
        perimeter = self.wetted_perimeter(y)
        if perimeter < 1e-6:
            return 0.0
        return area / perimeter


class RectangularCrossSection(BaseCrossSection):
    """Represents a simple rectangular cross-section."""
    def __init__(self, width: float):
        if width <= 0:
            raise ValueError("Width must be positive.")
        self.width = width

    def area(self, y: float) -> float:
        """Calculate the wetted area for a given water depth y."""
        return self.width * max(0, y)

    def top_width(self, y: float) -> float:
        """Calculate the top width for a given water depth y."""
        return self.width

    def wetted_perimeter(self, y: float) -> float:
        """Calculate the wetted perimeter for a given water depth y."""
        return self.width + 2 * max(0, y)


class TrapezoidalCrossSection(BaseCrossSection):
    """Represents a trapezoidal cross-section."""
    def __init__(self, bottom_width: float, side_slope: float):
        if bottom_width <= 0:
            raise ValueError("Bottom width must be positive.")
        if side_slope < 0:
            raise ValueError("Side slope cannot be negative.")
        self.bottom_width = bottom_width
        self.side_slope = side_slope # z, where slope is zH:1V

    def area(self, y: float) -> float:
        """Calculate the wetted area for a given water depth y."""
        y = max(0, y)
        return (self.bottom_width + self.side_slope * y) * y

    def top_width(self, y: float) -> float:
        """Calculate the top width for a given water depth y."""
        y = max(0, y)
        return self.bottom_width + 2 * self.side_slope * y

    def wetted_perimeter(self, y: float) -> float:
        """Calculate the wetted perimeter for a given water depth y."""
        y = max(0, y)
        side_length = y * (1 + self.side_slope**2)**0.5
        return self.bottom_width + 2 * side_length
