"""
River Reach Module
==================

This module defines the RiverReach class, which represents a segment
of a river, composed of a series of cross-sections.
"""
from typing import List
import numpy as np
from .cross_section import BaseCrossSection

class RiverReach:
    """Represents a segment of a river."""
    def __init__(self,
                 cross_sections: List[BaseCrossSection],
                 lengths: np.ndarray,
                 slope: float,
                 manning_n: float):

        if not all(isinstance(cs, BaseCrossSection) for cs in cross_sections):
            raise TypeError("All elements in cross_sections must be instances of BaseCrossSection.")

        self.num_sections = len(cross_sections)

        if len(lengths) != self.num_sections - 1:
            raise ValueError(f"Number of lengths ({len(lengths)}) must be one less than "
                             f"the number of cross-sections ({self.num_sections}).")

        if slope < 0:
            raise ValueError("Slope cannot be negative.")

        if manning_n <= 0:
            raise ValueError("Manning's n must be positive.")

        self.cross_sections = cross_sections
        self.lengths = np.array(lengths, dtype=float)
        self.slope = slope
        self.manning_n = manning_n

    def areas_from_Z(self, Z, Z_bed):
        """Calculates cross-sectional areas from water surface and bed elevations."""
        y = Z - Z_bed
        # Ensure water depth is non-negative
        y[y < 0] = 0
        return np.array([cs.area(y_i) for cs, y_i in zip(self.cross_sections, y)])

    def lengths_for_volume(self):
        """
        Returns an array of representative lengths for each node for volume calculation.
        Each node's volume is its cross-sectional area times this representative length.
        """
        if self.num_sections == 1:
            return np.array([0.0]) # A single point has no volume

        v_lengths = np.zeros(self.num_sections)
        # First node represents half of the first segment
        v_lengths[0] = self.lengths[0] / 2.0
        # Last node represents half of the last segment
        v_lengths[-1] = self.lengths[-1] / 2.0
        # Interior nodes represent half of the upstream and half of the downstream segment
        for i in range(1, self.num_sections - 1):
            v_lengths[i] = (self.lengths[i-1] + self.lengths[i]) / 2.0
        return v_lengths
