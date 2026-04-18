import os
import sys

import numpy as np


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hydro_model.generic_model_adapter import GenericModelAdapter


class _ExternalUnknownModel:
    def __init__(self) -> None:
        self.last_call = None

    def simulate(self, inflow, rain):
        self.last_call = {
            "inflow": np.asarray(inflow, dtype=float),
            "rain": np.asarray(rain, dtype=float),
        }
        return {"downstream_flow": self.last_call["inflow"] + self.last_call["rain"]}


def test_generic_model_adapter_maps_external_model_io_to_standard_contracts() -> None:
    external_model = _ExternalUnknownModel()
    adapter = GenericModelAdapter(
        external_model=external_model,
        input_mapping={
            "Q_in_reservoir": "inflow",
            "rainfall": "rain",
        },
        output_mapping={
            "downstream_flow": "Q_out_reservoir",
        },
        predict_fn_name="simulate",
    )

    result = adapter.run_simulation(
        {
            "Q_in_reservoir": np.array([1.0, 2.5]),
            "rainfall": np.array([0.2, 0.3]),
            "unused_standard_key": np.array([99.0, 99.0]),
        }
    )

    np.testing.assert_allclose(external_model.last_call["inflow"], [1.0, 2.5])
    np.testing.assert_allclose(external_model.last_call["rain"], [0.2, 0.3])
    assert set(result) == {"Q_out_reservoir"}
    np.testing.assert_allclose(result["Q_out_reservoir"], [1.2, 2.8])
