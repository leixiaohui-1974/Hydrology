import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from preissmann_model.cross_section import RectangularCrossSection
from preissmann_model.model import HydraulicModel
from preissmann_model.reach import RiverReach
from preissmann_model.structures import Gate, Pump, Weir


def build_model():
    cross_sections = [RectangularCrossSection(width=10.0) for _ in range(5)]
    reach = RiverReach(
        cross_sections=cross_sections,
        lengths=np.full(4, 100.0),
        slope=0.001,
        manning_n=0.03,
    )
    model = HydraulicModel(
        name="TestReach",
        reach=reach,
        dt=10.0,
        downstream_level=1.5,
        initial_Z=[1.9, 1.8, 1.7, 1.6, 1.5],
        initial_Q=[5.0, 5.0, 5.0, 5.0, 5.0],
    )
    return model


def test_validator_repairs_invalid_state():
    model = build_model()
    bad_Z = np.array([np.nan, -10.0, 100.0, 1.6, 1.5])
    bad_Q = np.array([np.nan, 1e8, -1e8, 5.0, 5.0])
    fixed_Z, fixed_Q, report = model.validator.repair_state(
        bad_Z,
        bad_Q,
        model.Z_bed,
        model.Z,
        model.Q,
        model.downstream_level,
        {"Q_inflow": 4.0},
    )
    assert report.valid
    assert report.repaired
    assert np.isfinite(fixed_Z).all()
    assert np.isfinite(fixed_Q).all()
    assert fixed_Q[0] == 4.0
    assert fixed_Z[-1] >= model.downstream_level


def test_hydraulic_model_step_keeps_valid_state():
    model = build_model()
    for _ in range(3):
        model.step({"Q_inflow": 6.0}, dt=10.0)
    assert np.isfinite(model.Z).all()
    assert np.isfinite(model.Q).all()
    assert abs(model.Z[-1] - model.downstream_level) < 1e-6
    assert model.last_validation_report["valid"]


def test_structure_linearizations_are_finite():
    gate = Gate("G1", node_index=2, opening_height=1.0, width=2.0)
    pump = Pump("P1", node_index=2, curve_coeffs=(0.01, 0.5, 1.0))
    weir = Weir("W1", node_index=2, crest_elevation=0.5, width=3.0)
    for structure in (gate, pump, weir):
        coeffs, rhs = structure.get_linearized_equation(2.0, 1.0, 3.0)
        assert np.isfinite(rhs)
        assert all(np.isfinite(value) for value in coeffs.values())
