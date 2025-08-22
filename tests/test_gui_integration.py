import unittest
import sys
import os
import numpy as np

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.main import _generate_config_dict
from common.config_parser import ConfigParser
from preissmann_model.model import HydraulicModel
from preissmann_model.structures import Weir

class TestGuiIntegration(unittest.TestCase):

    def setUp(self):
        """Set up a mock GUI data object for testing."""
        self.mock_gui_data = {
            "nodes": {
                "node-1": {
                    "id": "node-1",
                    "name": "MyRiver",
                    "type": "HydraulicModel",
                    "params": {
                        "dt": 60,
                        "downstream_level": 10.0,
                        # The reach would be a complex nested object in a real scenario
                        "reach": {"type": "RiverReach", "parameters": {
                            "num_nodes": 10, "length": 1000, "slope": 0.001, "manning_n": 0.03,
                            "cross_sections": [{"type": "RectangularCrossSection", "parameters": {"width": 10}}]
                        }}
                    }
                },
                "node-2": {
                    "id": "node-2",
                    "name": "UpstreamWeir",
                    "type": "Weir",
                    "params": {
                        "parent_reach": "MyRiver", # Key to link to the parent
                        "node_index": 4,
                        "crest_elevation": 12.0,
                        "width": 20.0
                    }
                }
            },
            "connections": [],
            "sim_params": {"dt_seconds": 60, "num_steps": 10},
            "global_inputs": {"MyRiver": {"values": [50]*10}}
        }

    def test_nested_component_generation(self):
        """Test if the config dict correctly nests structures within their parent."""
        print("\nRunning test_nested_component_generation...")
        config_dict = _generate_config_dict(self.mock_gui_data)

        self.assertEqual(len(config_dict["components"]), 1) # Only one top-level component

        hydraulic_model_config = config_dict["components"][0]
        self.assertEqual(hydraulic_model_config["name"], "MyRiver")

        self.assertIn("structures", hydraulic_model_config["parameters"])
        self.assertEqual(len(hydraulic_model_config["parameters"]["structures"]), 1)

        weir_config = hydraulic_model_config["parameters"]["structures"][0]
        self.assertEqual(weir_config["name"], "UpstreamWeir")
        self.assertEqual(weir_config["type"], "Weir")
        self.assertNotIn("parent_reach", weir_config["parameters"]) # Check that it was removed
        self.assertEqual(weir_config["parameters"]["node_index"], 4)
        print("Nested component generation test passed.")

    def test_simulation_build_from_nested_gui_config(self):
        """Test if the ConfigParser can build a simulation from the nested config."""
        print("\nRunning test_simulation_build_from_nested_gui_config...")
        config_dict = _generate_config_dict(self.mock_gui_data)

        parser = ConfigParser(config_dict, base_path='.')
        controller, _, _ = parser.build_simulation()

        self.assertIn("MyRiver", controller.components)
        model_component = controller.components["MyRiver"]
        self.assertIsInstance(model_component, HydraulicModel)

        self.assertEqual(len(model_component.structures), 1)
        weir_structure = model_component.structures[0]
        self.assertIsInstance(weir_structure, Weir)
        self.assertEqual(weir_structure.name, "UpstreamWeir")
        print("Simulation build with nested components test passed.")


if __name__ == '__main__':
    unittest.main()
