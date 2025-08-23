from common.base_model import BaseModelComponent

class SimplePassthroughModel(BaseModelComponent):
    """
    A very simple model that passes rainfall through with a coefficient.
    This is used for testing the Real-Twin framework without depending on
    complex hydrological models.
    """
    def __init__(self, name: str, coeff: float = 0.5, **kwargs):
        super().__init__(name)
        self.coeff = coeff

    def step(self, inflows: dict, dt: float):
        """
        The model logic for one time step.
        """
        rainfall = inflows.get('rainfall', 0.0)
        upstream_inflow = sum(v for k, v in inflows.items() if k not in ['rainfall', 'pet', 'temperature'])

        # This model is extremely simple: runoff is a fraction of rainfall.
        # We convert rainfall (mm/day) to a flow rate (m3/s) for consistency.
        # This requires area, which this simple model doesn't have.
        # Let's simplify even further and assume the 'rainfall' input is already a flow rate.

        self.outflow = rainfall * self.coeff + upstream_inflow
