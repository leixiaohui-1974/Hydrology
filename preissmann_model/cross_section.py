"""
Cross-Section Module
====================

This module defines the classes and functions related to the geometry
of a river cross-section.
"""
from abc import ABC, abstractmethod
import numpy as np

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
        if bottom_width <= 0 or side_slope < 0:
            raise ValueError("Bottom width must be positive and side slope must be non-negative.")
        self.bottom_width = bottom_width
        self.side_slope = side_slope # Ratio of horizontal to vertical (z in z:1)

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
        from math import sqrt
        y = max(0, y)
        return self.bottom_width + 2 * y * sqrt(1 + self.side_slope**2)


class IrregularCrossSection(BaseCrossSection):
    """Represents an irregular cross-section defined by station-elevation points."""
    def __init__(self, points: list[tuple[float, float]]):
        if len(points) < 2:
            raise ValueError("An irregular cross-section must have at least 2 points.")

        # Sort points by station (x-coordinate)
        self.points = np.array(sorted(points, key=lambda p: p[0]))
        self.stations = self.points[:, 0]
        self.elevations = self.points[:, 1]
        self.thalweg_elevation = np.min(self.elevations)

    def _get_wetted_points(self, y: float) -> np.ndarray:
        """Helper to get the points and interpolated water surface intersection points."""
        y = max(0, y)
        water_surface_elev = self.thalweg_elevation + y

        # Find points below the water surface
        wetted_indices = np.where(self.elevations <= water_surface_elev)[0]
        if len(wetted_indices) == 0:
            return np.array([])

        all_points = []

        # Find the leftmost intersection with the water surface
        left_boundary_idx = wetted_indices[0]
        if left_boundary_idx > 0:
            p1 = self.points[left_boundary_idx - 1]
            p2 = self.points[left_boundary_idx]
            # Interpolate to find the exact intersection point
            interp_x = np.interp(water_surface_elev, [p1[1], p2[1]], [p1[0], p2[0]])
            all_points.append([interp_x, water_surface_elev])

        # Add all fully wetted points
        all_points.extend(self.points[wetted_indices])

        # Find the rightmost intersection with the water surface
        right_boundary_idx = wetted_indices[-1]
        if right_boundary_idx < len(self.points) - 1:
            p1 = self.points[right_boundary_idx]
            p2 = self.points[right_boundary_idx + 1]
            # Interpolate to find the exact intersection point
            interp_x = np.interp(water_surface_elev, [p1[1], p2[1]], [p1[0], p2[0]])
            all_points.append([interp_x, water_surface_elev])

        return np.array(sorted(all_points, key=lambda p: p[0]))

    def area(self, y: float) -> float:
        """Calculate the wetted area using the trapezoidal rule."""
        wetted_points = self._get_wetted_points(y)
        if len(wetted_points) < 2:
            return 0.0

        water_surface_elev = self.thalweg_elevation + y

        # We want the area between the ground and the water surface.
        # We can integrate this using the trapezoidal rule.
        # The y-values for the integration are the water depths at each station.
        depths = water_surface_elev - wetted_points[:, 1]
        stations = wetted_points[:, 0]

        return np.trapz(depths, stations)

    def top_width(self, y: float) -> float:
        """Calculate the top width at the water surface."""
        wetted_points = self._get_wetted_points(y)
        if len(wetted_points) < 2:
            return 0.0
        return wetted_points[-1][0] - wetted_points[0][0]

    def wetted_perimeter(self, y: float) -> float:
        """Calculate the wetted perimeter by summing segment lengths."""
        wetted_points = self._get_wetted_points(y)
        if len(wetted_points) < 2:
            return 0.0
        # Calculate distance between consecutive points
        return np.sum(np.sqrt(np.sum(np.diff(wetted_points, axis=0)**2, axis=1)))
