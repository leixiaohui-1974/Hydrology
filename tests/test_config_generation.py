import unittest
import sys
import os

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.config_generator import generate_config_from_gui_data

class TestConfigGeneration(unittest.TestCase):

    def test_simple_hydrological_network(self):
        """
        Tests the config generation for a simple network with one catchment
        and one outlet, connected.
        """
        gui_data = {
            "nodes": {
                "node1": {"id": "node1", "name": "Catchment1", "type": "HydrologicalModel", "params": {}},
                "node2": {"id": "node2", "name": "Outlet1", "type": "Outlet", "params": {}}
            },
            "connections": [
                {"from": "node1", "to": "node2"}
            ]
        }

        config = generate_config_from_gui_data(gui_data)

        # Check components
        self.assertEqual(len(config["components"]), 2)
        component_names = {c["name"] for c in config["components"]}
        self.assertIn("Catchment1", component_names)
        self.assertIn("Outlet1", component_names)

        # Check network
        self.assertEqual(len(config["network"]), 1)
        connection = config["network"][0]
        self.assertEqual(connection["from"], "Catchment1")
        self.assertEqual(connection["to"], "Outlet1")

    def test_2d_model_with_generated_mesh(self):
        """
        Tests that the config correctly uses the 'generated_mesh_file'
        parameter for a 2D model.
        """
        gui_data = {
            "nodes": {
                "node1": {
                    "id": "node1",
                    "name": "2D_Area",
                    "type": "HydraulicModel2D",
                    "params": {
                        "mesh_file": "original.json",
                        "generated_mesh_file": "temp/generated.json"
                    }
                }
            },
            "connections": []
        }

        config = generate_config_from_gui_data(gui_data)

        self.assertEqual(len(config["components"]), 1)
        component = config["components"][0]
        self.assertEqual(component["name"], "2D_Area")
        self.assertEqual(component["type"], "HydraulicModel2D")

        # Check that the generated mesh file is prioritized
        self.assertEqual(component["parameters"]["mesh_file"], "temp/generated.json")
        self.assertIn("generated_mesh_file", component["parameters"])

    def test_hydraulic_structure_nesting(self):
        """
        Tests that a hydraulic structure (e.g., a Gate) is correctly nested
        within its parent reach in the generated config.
        """
        gui_data = {
            "nodes": {
                "reach1": {"id": "reach1", "name": "MainRiver", "type": "HydraulicModel", "params": {}},
                "gate1": {"id": "gate1", "name": "ControlGate", "type": "Gate", "params": {"parent_reach": "MainRiver"}}
            },
            "connections": []
        }

        config = generate_config_from_gui_data(gui_data)

        # Should only be one top-level component (the reach)
        self.assertEqual(len(config["components"]), 1)
        reach_component = config["components"][0]
        self.assertEqual(reach_component["name"], "MainRiver")

        # The gate should be in the 'structures' list of the reach
        self.assertIn("structures", reach_component["parameters"])
        self.assertEqual(len(reach_component["parameters"]["structures"]), 1)

        gate_config = reach_component["parameters"]["structures"][0]
        self.assertEqual(gate_config["name"], "ControlGate")
        self.assertEqual(gate_config["type"], "Gate")

if __name__ == '__main__':
    unittest.main()
