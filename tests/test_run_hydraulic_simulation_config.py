import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Hydrology.workflows.run_hydraulic_simulation import run_simulation, run_canal_scenario

class TestHydraulicSimulationConfig(unittest.TestCase):
    @patch('Hydrology.workflows.run_hydraulic_simulation.load_case_config')
    @patch('Hydrology.workflows.run_hydraulic_simulation.run_canal_scenario')
    def test_run_simulation_canal(self, mock_run_canal_scenario, mock_load_case_config):
        mock_load_case_config.return_value = {
            "project_type": "canal",
            "hydraulics": {
                "solver": {
                    "method": "advanced_preconditioned",
                    "params": {
                        "max_iterations": 200
                    }
                }
            }
        }
        
        # Test routing to canal scenario
        run_simulation("test_case_id", "scenario")
        mock_run_canal_scenario.assert_called_once_with("test_case_id")

    @patch('Hydrology.workflows.run_hydraulic_simulation.load_case_config')
    @patch('hydromind_control_server.src.case_config_loader.load_case_config', create=True)
    @patch('run_real_validation._resolve_case_class', create=True)
    @patch('run_real_validation._get_station_chain', create=True)
    def test_run_canal_scenario_parsing(self, mock_get_chain, mock_resolve_cls, mock_mbd_config, mock_load_case_config):
        # Mock dependencies in sys.modules
        sys.modules['hydromind_control_server'] = MagicMock()
        sys.modules['hydromind_control_server.src'] = MagicMock()
        sys.modules['hydromind_control_server.src.case_config_loader'] = MagicMock()
        sys.modules['run_real_validation'] = MagicMock()
        
        # We need to test the actual code in run_canal_scenario
        # However, run_canal_scenario does dynamic imports:
        # from hydromind_control_server.src.case_config_loader import load_case_config
        
        # Set up mocks
        mock_case_cls = MagicMock()
        mock_case_instance = MagicMock()
        mock_case_cls.return_value = mock_case_instance
        mock_case_instance.run_simulation.return_value = {"dt": 1.0}
        
        mock_resolve_cls.return_value = (mock_case_cls, None)
        mock_get_chain.return_value = ["A", "B", "C"]
        
        mock_mbd_cfg = MagicMock()
        mock_mbd_cfg.case_name = "test_case"
        mock_mbd_cfg.project_type = "canal"
        mock_mbd_config.return_value = mock_mbd_cfg
        
        mock_load_case_config.return_value = {
            "project_type": "canal",
            "knowledge": {
                "solver_options": {"some_opt": 1}
            },
            "hydraulics": {
                "solver": {
                    "method": "advanced_preconditioned",
                    "params": {
                        "max_iterations": 200,
                        "convergence_tol": 1e-5
                    }
                }
            }
        }
        
        # Need to patch the imports inside the function
        with patch.dict('sys.modules', {
            'hydromind_control_server.src.case_config_loader': MagicMock(load_case_config=mock_mbd_config),
            'run_real_validation': MagicMock(_resolve_case_class=mock_resolve_cls, _get_station_chain=mock_get_chain)
        }):
            result = run_canal_scenario("test_case_id")
            
        self.assertEqual(result["mode"], "scenario")
        self.assertEqual(result["status"], "completed")
        
        # Verify that the case was initialized with the correct runtime_config
        # Call signature: case_cls(case_id, runtime_config, n_stations=len(station_chain))
        args, kwargs = mock_case_cls.call_args
        runtime_config = args[1]
        
        self.assertEqual(runtime_config["solver_method"], "advanced_preconditioned")
        self.assertEqual(runtime_config["solver_params"]["max_iterations"], 200)
        self.assertEqual(runtime_config["solver_params"]["convergence_tol"], 1e-5)
        self.assertEqual(runtime_config["solver_options"]["some_opt"], 1)

if __name__ == '__main__':
    unittest.main()
