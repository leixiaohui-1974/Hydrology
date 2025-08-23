import numpy as np

class Sensor:
    """
    Base class for a virtual sensor in the Real-Twin framework.
    """
    def __init__(self, name, location_id, error_std_dev=0.0):
        self.name = name
        self.location_id = location_id  # ID of the component it's measuring (e.g., 'Catchment1')
        self.error_std_dev = error_std_dev
        self.is_faulty = False
        self.fault_type = None

    def set_fault_state(self, is_faulty, fault_type=None):
        """
        Manually set the fault state of the sensor.

        Args:
            is_faulty (bool): True to activate fault, False to deactivate.
            fault_type (str, optional): 'clogging', 'outage', 'drift'. Defaults to None.
        """
        self.is_faulty = is_faulty
        self.fault_type = fault_type
        if fault_type == 'drift':
            self.drift_value = np.random.randn() * 5 # A random drift value

    def sample(self, true_value):
        """
        Samples the true value, adding random noise and simulating faults.
        """
        if self.is_faulty:
            if self.fault_type == 'clogging':
                return 0.0
            elif self.fault_type == 'outage':
                return np.nan
            elif self.fault_type == 'drift':
                return true_value + self.drift_value

        # Apply random noise
        noise = np.random.normal(0, self.error_std_dev)
        return true_value + noise

class RainGauge(Sensor):
    """
    A virtual rain gauge.
    """
    def __init__(self, name, location_id, **kwargs):
        super().__init__(name, location_id, **kwargs)
        # In a real scenario, this would sample from a 2D rainfall field.
        # Here, we assume it samples from a column in a dataframe.
        # The location_id corresponds to the rainfall column name, e.g., 'rainfall_1'.

class FlowGauge(Sensor):
    """
    A virtual flow gauge.
    """
    def __init__(self, name, location_id, **kwargs):
        super().__init__(name, location_id, **kwargs)
        # The location_id corresponds to the component name whose outflow is measured.
