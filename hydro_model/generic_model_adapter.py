"""Generic adapter for mapping external model data flows to standard HydroMind contracts."""

from typing import Any, Callable, Dict, Optional
import numpy as np

class GenericModelAdapter:
    """
    Standardizes external unknown models into the HydroMind ecosystem.
    Maps system standard inputs (e.g., Q_in_reservoir, rainfall) to model-specific inputs,
    runs the model, and maps outputs back to standard contract keys (e.g., Q_out_reservoir).
    """
    def __init__(
        self,
        external_model: Any,
        input_mapping: Dict[str, str],
        output_mapping: Dict[str, str],
        predict_fn_name: str = "predict"
    ):
        """
        Args:
            external_model: The instance of the external model (e.g., a PyTorch model, Scikit-Learn, or custom function).
            input_mapping: Mapping from standard HydroMind keys to external model argument keys.
                           Example: {"Q_in_reservoir": "x", "rainfall": "rain"}
            output_mapping: Mapping from external model output keys/indices to standard HydroMind keys.
                            Example: {0: "Q_out_reservoir"} or {"y": "Q_out_reservoir"}
            predict_fn_name: Name of the method to call on the external model (e.g., 'predict', '__call__', 'simulate').
        """
        self.model = external_model
        self.input_mapping = input_mapping
        self.output_mapping = output_mapping
        self.predict_fn_name = predict_fn_name

    def run_simulation(self, standard_inputs: Dict[str, Any], params: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Runs the external model using standard inputs and parameters, returning standard outputs.
        """
        # Prepare inputs for the external model
        model_inputs = {}
        for std_key, ext_key in self.input_mapping.items():
            if std_key in standard_inputs:
                model_inputs[ext_key] = standard_inputs[std_key]
        
        # If parameters are provided, we can pass them either as inputs or set them on the model
        if params:
            model_inputs.update(params)

        # Run the external model
        predict_fn = getattr(self.model, self.predict_fn_name, None)
        if predict_fn is None and callable(self.model):
            predict_fn = self.model
            
        if not predict_fn:
            raise ValueError(f"Model does not have a callable method '{self.predict_fn_name}'")

        # Handle different signature types
        try:
            raw_output = predict_fn(**model_inputs)
        except TypeError:
            # Fallback to positional if kwargs fail
            raw_output = predict_fn(*model_inputs.values())

        # Map back to standard outputs
        standard_outputs = {}
        if isinstance(raw_output, dict):
            for ext_key, std_key in self.output_mapping.items():
                standard_outputs[std_key] = raw_output.get(ext_key)
        elif isinstance(raw_output, (list, tuple, np.ndarray)):
            # If output is a single array but mapping expects multiple, or just 1:1 mapping
            if len(self.output_mapping) == 1:
                std_key = list(self.output_mapping.values())[0]
                standard_outputs[std_key] = raw_output
            else:
                for idx, std_key in self.output_mapping.items():
                    standard_outputs[std_key] = raw_output[int(idx)]
        else:
            # Scalar or single object
            if len(self.output_mapping) == 1:
                std_key = list(self.output_mapping.values())[0]
                standard_outputs[std_key] = raw_output

        return standard_outputs
