"""HydroClaude adapter for mapping HydroClaude inputs/outputs to standard HydroMind contracts."""

from typing import Any, Dict, Optional
import numpy as np

from hydro_model.generic_model_adapter import GenericModelAdapter

class HydroClaudeAdapter(GenericModelAdapter):
    """
    Standardizes HydroClaude model into the HydroMind ecosystem.
    Extends GenericModelAdapter to map HydroClaude inputs/outputs to hydromind-contracts JSON schemas.
    """
    def __init__(
        self,
        external_model: Any,
        input_mapping: Optional[Dict[str, str]] = None,
        output_mapping: Optional[Dict[str, str]] = None,
        predict_fn_name: str = "simulate"
    ):
        """
        Args:
            external_model: The instance of the HydroClaude model.
            input_mapping: Mapping from standard HydroMind keys to HydroClaude argument keys.
            output_mapping: Mapping from HydroClaude output keys/indices to standard HydroMind keys.
            predict_fn_name: Name of the method to call on the HydroClaude model.
        """
        # Default mappings for HydroClaude to hydromind-contracts
        default_input_mapping = {
            "rainfall_multiplier": "rainfall_multiplier",
            "soil_storage_scale": "soil_storage_scale",
            "baseflow_recession_factor": "baseflow_recession_factor",
            "input_data": "input_data"
        }
        
        default_output_mapping = {
            0: "Q_out_reservoir"
        }
        
        # Override defaults with provided mappings
        if input_mapping:
            default_input_mapping.update(input_mapping)
        if output_mapping:
            default_output_mapping.update(output_mapping)
            
        super().__init__(
            external_model=external_model,
            input_mapping=default_input_mapping,
            output_mapping=default_output_mapping,
            predict_fn_name=predict_fn_name
        )
