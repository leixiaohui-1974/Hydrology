from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np


@dataclass
class HydraulicStateReport:
    valid: bool
    repaired: bool
    issues: list[str]
    max_depth: float
    max_abs_flow: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HydraulicStateValidator:
    """Validate and repair Preissmann model states before they are committed."""

    def __init__(
        self,
        reach,
        min_depth: float = 1e-6,
        max_depth: float = 50.0,
        max_abs_flow: float = 1e4,
        max_stage_jump: float = 5.0,
        max_flow_jump: float = 2e3,
    ) -> None:
        self.reach = reach
        self.min_depth = min_depth
        self.max_depth = max_depth
        self.max_abs_flow = max_abs_flow
        self.max_stage_jump = max_stage_jump
        self.max_flow_jump = max_flow_jump

    def repair_state(
        self,
        Z: np.ndarray,
        Q: np.ndarray,
        Z_bed: np.ndarray,
        previous_Z: np.ndarray,
        previous_Q: np.ndarray,
        downstream_level: float,
        inflows: dict[str, float],
    ) -> tuple[np.ndarray, np.ndarray, HydraulicStateReport]:
        issues: list[str] = []
        repaired = False
        Z = np.asarray(Z, dtype=float).copy()
        Q = np.asarray(Q, dtype=float).copy()
        previous_Z = np.asarray(previous_Z, dtype=float)
        previous_Q = np.asarray(previous_Q, dtype=float)

        invalid_Z = ~np.isfinite(Z)
        invalid_Q = ~np.isfinite(Q)
        if invalid_Z.any():
            Z[invalid_Z] = previous_Z[invalid_Z]
            issues.append("non-finite stage repaired from previous state")
            repaired = True
        if invalid_Q.any():
            Q[invalid_Q] = previous_Q[invalid_Q]
            issues.append("non-finite discharge repaired from previous state")
            repaired = True

        min_stage = Z_bed + self.min_depth
        if (Z < min_stage).any():
            Z = np.maximum(Z, min_stage)
            issues.append("sub-bed stage clipped to minimum depth")
            repaired = True

        if (Z - Z_bed > self.max_depth).any():
            Z = np.minimum(Z, Z_bed + self.max_depth)
            issues.append("excessive depth clipped")
            repaired = True

        if np.abs(Q).max(initial=0.0) > self.max_abs_flow:
            Q = np.clip(Q, -self.max_abs_flow, self.max_abs_flow)
            issues.append("excessive discharge clipped")
            repaired = True

        stage_jump = np.abs(Z - previous_Z)
        if stage_jump.max(initial=0.0) > self.max_stage_jump:
            factor = self.max_stage_jump / max(stage_jump.max(), 1e-9)
            Z = previous_Z + (Z - previous_Z) * factor
            issues.append("stage jump damped")
            repaired = True

        flow_jump = np.abs(Q - previous_Q)
        if flow_jump.max(initial=0.0) > self.max_flow_jump:
            factor = self.max_flow_jump / max(flow_jump.max(), 1e-9)
            Q = previous_Q + (Q - previous_Q) * factor
            issues.append("discharge jump damped")
            repaired = True

        if "Q_inflow" in inflows:
            Q[0] = float(inflows["Q_inflow"])
        if "Z_inflow" in inflows:
            Z[0] = max(float(inflows["Z_inflow"]), min_stage[0])
        Z[-1] = max(downstream_level, min_stage[-1])

        valid = np.isfinite(Z).all() and np.isfinite(Q).all() and np.all(Z >= min_stage)
        report = HydraulicStateReport(
            valid=valid,
            repaired=repaired,
            issues=issues,
            max_depth=float(np.max(Z - Z_bed)) if Z.size else 0.0,
            max_abs_flow=float(np.max(np.abs(Q))) if Q.size else 0.0,
        )
        return Z, Q, report
