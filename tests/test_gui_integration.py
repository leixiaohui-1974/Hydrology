import unittest
import sys
import os
import shutil
import numpy as np

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.main import _generate_config_dict
from common.config_parser import ConfigParser
from preissmann_model.model import HydraulicModel
from preissmann_model.structures import Weir
from model_2d.model import Model2D


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

    def test_2d_model_creation_from_gui(self):
        """Test if a 2D model component can be created from GUI data."""
        print("\nRunning test_2d_model_creation_from_gui...")

        # Add a 2D model to the mock data
        self.mock_gui_data["nodes"]["node-3"] = {
            "id": "node-3",
            "name": "2DFloodplain",
            "type": "HydraulicModel2D",
            "params": {
                "mesh_file": "channel_mesh.json", # Using an existing file for the test
                "dem_file": "gis_data/dem.tif"
            }
        }
        self.mock_gui_data["connections"].append({"from": "node-1", "to": "node-3"})

        config_dict = _generate_config_dict(self.mock_gui_data)

        # Verify the config dictionary has the 2D model as a top-level component
        self.assertEqual(len(config_dict["components"]), 2)
        component_names = [c['name'] for c in config_dict['components']]
        self.assertIn("2DFloodplain", component_names)

        # Verify the simulation can be built
        # Note: This requires the dummy mesh/dem files to exist at the specified paths
        parser = ConfigParser(config_dict, base_path='.')
        controller, _, _ = parser.build_simulation()

        self.assertIn("2DFloodplain", controller.components)
        model_2d_comp = controller.components["2DFloodplain"]

        self.assertIsInstance(model_2d_comp, Model2D)

        # Verify connection
        self.assertIn("2DFloodplain", controller.network["MyRiver"])
        print("2D model creation from GUI data test passed.")

    def test_mesh_generation_service(self):
        """Test the mesh generation service."""
        print("\nRunning test_mesh_generation_service...")
        from gui.main import generate_mesh_from_params
        import json

        params = {
            'length': 10, 'width': 5, 'num_x': 4, 'num_y': 3,
            'output_filename': 'test_mesh.json'
        }

        result = generate_mesh_from_params(params)

        self.assertIn('mesh_path', result)
        self.assertIsNone(result.get('error'))

        mesh_path = result['mesh_path']
        self.assertTrue(os.path.exists(mesh_path))

        with open(mesh_path, 'r') as f:
            data = json.load(f)

        self.assertIn('points', data)
        self.assertIn('triangles', data)
        self.assertEqual(len(data['points']), 12) # 4 * 3

        # Clean up
        temp_dir = 'temp'
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        print("Mesh generation service test passed.")


if __name__ == '__main__':
    unittest.main()
