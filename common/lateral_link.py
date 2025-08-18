"""
1D-2D Lateral Link Component Module
===================================
This module provides the LateralLink class, which models the bi-directional
exchange of water between a 1D river reach and a 2D floodplain area.
"""
import numpy as np
from .base_model import BaseModelComponent

class LateralLink(BaseModelComponent):
    """
    A LateralLink component calculates flow over a weir (e.g., a levee)
    that connects a 1D river node to a 2D mesh cell.
    """
    def __init__(self, name: str, model_1d, node_1d_idx: int, model_2d, face_2d_idx: int,
                 crest_elevation: float, width: float, weir_coeff: float = 1.6):
        super().__init__(name)
        self.model_1d = model_1d
        self.node_1d_idx = node_1d_idx
        self.model_2d = model_2d
        self.face_2d_idx = face_2d_idx
        self.crest_elevation = crest_elevation
        self.width = width
        self.weir_coeff = weir_coeff
        self.outflow_to_1d = 0.0
        self.outflow_to_2d = 0.0

    def step(self, inflows: dict, dt: float):
        """
        Calculates the bi-directional exchange flow for one time step,
        including a volume-based limiter for stability.
        """
        Z_1d = self.model_1d.Z[self.node_1d_idx]
        face_2d = self.model_2d.mesh.faces[self.face_2d_idx]
        Z_2d = face_2d.z_bed + face_2d.h

        Q_exchange = 0.0

        if Z_1d > Z_2d and Z_1d > self.crest_elevation:
            head = Z_1d - self.crest_elevation
            Q_exchange = self.weir_coeff * self.width * head**(1.5)
            # Volume limiter
            node_reach = self.model_1d.reach
            dx_1d = (node_reach.lengths[self.node_1d_idx - 1] + node_reach.lengths[self.node_1d_idx]) / 2 if 0 < self.node_1d_idx < len(node_reach.lengths) else node_reach.lengths[0]
            area_1d = node_reach.cross_sections[self.node_1d_idx].area(Z_1d - self.model_1d.Z_bed[self.node_1d_idx])
            volume_1d = area_1d * dx_1d
            max_Q = volume_1d / dt
            Q_exchange = min(Q_exchange, max_Q)
            self.outflow_to_2d = Q_exchange
            self.outflow_to_1d = -Q_exchange
        elif Z_2d > Z_1d and Z_2d > self.crest_elevation:
            head = Z_2d - self.crest_elevation
            Q_exchange = self.weir_coeff * self.width * head**(1.5)
            # Volume limiter
            volume_2d = face_2d.h * face_2d.area
            max_Q = volume_2d / dt
            Q_exchange = min(Q_exchange, max_Q)
            self.outflow_to_1d = Q_exchange
            self.outflow_to_2d = -Q_exchange
        else:
            self.outflow_to_1d = 0.0
            self.outflow_to_2d = 0.0

        self.outflow = Q_exchange
