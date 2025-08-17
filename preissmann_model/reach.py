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
