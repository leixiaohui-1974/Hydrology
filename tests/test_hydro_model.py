"""Tests for the hydro_model module."""
import unittest
import sys
import os
import numpy as np
from unittest.mock import Mock, patch, MagicMock

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hydro_model.model import HydrologicalModel
from hydro_model.runoff import BaseRunoffModule, XAJModule, HymodModule, SCSModule
from hydro_model.routing import BaseRoutingModule, UnitHydrographModule
from common.base_model import BaseModelComponent


class MockRunoffModule(BaseRunoffModule):
    """Mock runoff module for testing."""
    
    def __init__(self, name="mock_runoff"):
        super().__init__(name)
        self.parameters = {'param1': 1.0, 'param2': 2.0}
    
    def step(self, inflows, dt):
        # Simple mock: return half of rainfall as runoff
        rainfall = inflows.get('rainfall', 0.0)
        return {'runoff': rainfall * 0.5}
    
    def get_results(self):
        return {'runoff_history': [1.0, 2.0, 3.0]}


class MockRoutingModule(BaseRoutingModule):
    """Mock routing module for testing."""
    
    def __init__(self, name="mock_routing"):
        super().__init__(name)
        self.parameters = {'lag_time': 2.0}
    
    def step(self, inflows, dt):
        # Simple mock: return runoff with some delay
        runoff = inflows.get('runoff', 0.0)
        return {'outflow': runoff * 0.8}
    
    def get_results(self):
        return {'outflow_history': [0.8, 1.6, 2.4]}


class MockSnowmeltModule(BaseRunoffModule):
    """Mock snowmelt module for testing."""
    
    def __init__(self, name="mock_snowmelt"):
        super().__init__(name)
        self.parameters = {'melt_factor': 3.0}
    
    def step(self, inflows, dt):
        # Simple mock: return temperature-based snowmelt
        temperature = inflows.get('temperature', 0.0)
        snowmelt = max(0, temperature - 0) * 0.1  # Simple degree-day method
        return {'snowmelt': snowmelt}
    
    def get_results(self):
        return {'snowmelt_history': [0.1, 0.2, 0.3]}


class TestHydrologicalModel(unittest.TestCase):
    """Test cases for HydrologicalModel class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_runoff = MockRunoffModule()
        self.mock_routing = MockRoutingModule()
        self.mock_snowmelt = MockSnowmeltModule()
    
    def test_init_with_runoff_only(self):
        """Test initialization with only runoff module."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff
        )
        
        self.assertEqual(model.name, "test_model")
        self.assertEqual(model.runoff_module, self.mock_runoff)
        self.assertIsNone(model.routing_module)
        self.assertIsNone(model.snowmelt_module)
        self.assertEqual(model.outflow_history, [])
    
    def test_init_with_all_modules(self):
        """Test initialization with all modules."""
        model = HydrologicalModel(
            name="full_model",
            runoff_module=self.mock_runoff,
            routing_module=self.mock_routing,
            snowmelt_module=self.mock_snowmelt
        )
        
        self.assertEqual(model.name, "full_model")
        self.assertEqual(model.runoff_module, self.mock_runoff)
        self.assertEqual(model.routing_module, self.mock_routing)
        self.assertEqual(model.snowmelt_module, self.mock_snowmelt)
    
    def test_init_invalid_runoff_module(self):
        """Test initialization with invalid runoff module."""
        with self.assertRaises(TypeError):
            HydrologicalModel(
                name="invalid_model",
                runoff_module="not_a_module"
            )
    
    def test_init_invalid_routing_module(self):
        """Test initialization with invalid routing module."""
        with self.assertRaises(TypeError):
            HydrologicalModel(
                name="invalid_model",
                runoff_module=self.mock_runoff,
                routing_module="not_a_module"
            )
    
    def test_init_invalid_snowmelt_module(self):
        """Test initialization with invalid snowmelt module."""
        with self.assertRaises(TypeError):
            HydrologicalModel(
                name="invalid_model",
                runoff_module=self.mock_runoff,
                snowmelt_module="not_a_module"
            )
    
    def test_step_runoff_only(self):
        """Test single step with runoff module only."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff
        )
        
        inflows = {'rainfall': 10.0, 'pet': 2.0}
        result = model.step(inflows, dt=1.0)
        
        # Should return runoff from mock module
        self.assertIn('runoff', result)
        self.assertEqual(result['runoff'], 5.0)  # 10.0 * 0.5
        self.assertEqual(len(model.outflow_history), 1)
        self.assertEqual(model.outflow_history[0], 5.0)
    
    def test_step_with_routing(self):
        """Test single step with runoff and routing modules."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff,
            routing_module=self.mock_routing
        )
        
        inflows = {'rainfall': 10.0, 'pet': 2.0}
        result = model.step(inflows, dt=1.0)
        
        # Should return outflow from routing module
        self.assertIn('outflow', result)
        self.assertEqual(result['outflow'], 4.0)  # 5.0 * 0.8
        self.assertEqual(len(model.outflow_history), 1)
        self.assertEqual(model.outflow_history[0], 4.0)
    
    def test_step_with_snowmelt(self):
        """Test single step with snowmelt module."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff,
            snowmelt_module=self.mock_snowmelt
        )
        
        inflows = {'rainfall': 10.0, 'pet': 2.0, 'temperature': 5.0}
        result = model.step(inflows, dt=1.0)
        
        # Should include snowmelt in the process
        self.assertIn('runoff', result)
        # Snowmelt should be added to rainfall before runoff calculation
        expected_total_input = 10.0 + 0.5  # rainfall + snowmelt
        expected_runoff = expected_total_input * 0.5
        self.assertEqual(result['runoff'], expected_runoff)
    
    def test_step_multiple_timesteps(self):
        """Test multiple time steps."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff,
            routing_module=self.mock_routing
        )
        
        # Run multiple steps
        for i in range(3):
            inflows = {'rainfall': (i + 1) * 5.0, 'pet': 2.0}
            model.step(inflows, dt=1.0)
        
        # Check history
        self.assertEqual(len(model.outflow_history), 3)
        expected_outflows = [2.0, 4.0, 6.0]  # (5*0.5*0.8, 10*0.5*0.8, 15*0.5*0.8)
        np.testing.assert_array_almost_equal(model.outflow_history, expected_outflows)
    
    def test_get_results(self):
        """Test get_results method."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff,
            routing_module=self.mock_routing,
            snowmelt_module=self.mock_snowmelt
        )
        
        # Run a step to generate some history
        inflows = {'rainfall': 10.0, 'pet': 2.0, 'temperature': 5.0}
        model.step(inflows, dt=1.0)
        
        results = model.get_results()
        
        # Should contain results from all modules
        self.assertIn('outflow_history', results)
        self.assertIn('runoff_module_results', results)
        self.assertIn('routing_module_results', results)
        self.assertIn('snowmelt_module_results', results)
        
        # Check specific values
        self.assertEqual(len(results['outflow_history']), 1)
        self.assertIn('runoff_history', results['runoff_module_results'])
        self.assertIn('outflow_history', results['routing_module_results'])
        self.assertIn('snowmelt_history', results['snowmelt_module_results'])
    
    def test_run_method(self):
        """Test the run method with time series data."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff
        )
        
        # Create test data
        rainfall = np.array([5.0, 10.0, 15.0, 8.0, 2.0])
        pet = np.array([2.0, 3.0, 4.0, 2.5, 1.5])
        
        results = model.run(rainfall, pet)
        
        # Check that results are returned
        self.assertIsInstance(results, dict)
        self.assertEqual(len(model.outflow_history), len(rainfall))
        
        # Check that outflow values are reasonable
        expected_outflows = rainfall * 0.5  # Based on mock module behavior
        np.testing.assert_array_almost_equal(model.outflow_history, expected_outflows)
    
    def test_error_handling_in_step(self):
        """Test error handling during step execution."""
        # Create a runoff module that raises an exception
        error_runoff = Mock(spec=BaseRunoffModule)
        error_runoff.step.side_effect = ValueError("Test error")
        
        model = HydrologicalModel(
            name="error_model",
            runoff_module=error_runoff
        )
        
        inflows = {'rainfall': 10.0, 'pet': 2.0}
        
        # Should propagate the error
        with self.assertRaises(ValueError):
            model.step(inflows, dt=1.0)
    
    def test_parameter_access(self):
        """Test access to module parameters."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff,
            routing_module=self.mock_routing
        )
        
        # Should be able to access parameters from modules
        self.assertEqual(model.runoff_module.parameters['param1'], 1.0)
        self.assertEqual(model.routing_module.parameters['lag_time'], 2.0)
    
    def test_inheritance_from_base_model_component(self):
        """Test that HydrologicalModel properly inherits from BaseModelComponent."""
        model = HydrologicalModel(
            name="test_model",
            runoff_module=self.mock_runoff
        )
        
        self.assertIsInstance(model, BaseModelComponent)
        self.assertTrue(hasattr(model, 'name'))
        self.assertTrue(hasattr(model, 'step'))
        self.assertTrue(hasattr(model, 'get_results'))


class TestRunoffModules(unittest.TestCase):
    """Test cases for specific runoff modules."""
    
    def test_xaj_module_initialization(self):
        """Test XAJ module initialization."""
        try:
            from hydro_model.runoff import XAJModule
            
            # Test with default parameters
            xaj = XAJModule(name="test_xaj")
            self.assertEqual(xaj.name, "test_xaj")
            self.assertIsInstance(xaj.parameters, dict)
            
            # Test with custom parameters
            custom_params = {'K': 0.5, 'B': 0.3, 'IM': 0.01}
            xaj_custom = XAJModule(name="custom_xaj", **custom_params)
            self.assertEqual(xaj_custom.parameters['K'], 0.5)
            
        except ImportError:
            self.skipTest("XAJ module not available")
    
    def test_hymod_module_initialization(self):
        """Test HYMOD module initialization."""
        try:
            from hydro_model.runoff import HymodModule
            
            hymod = HymodModule(name="test_hymod")
            self.assertEqual(hymod.name, "test_hymod")
            self.assertIsInstance(hymod.parameters, dict)
            
        except ImportError:
            self.skipTest("HYMOD module not available")
    
    def test_scs_module_initialization(self):
        """Test SCS module initialization."""
        try:
            from hydro_model.runoff import SCSModule
            
            scs = SCSModule(name="test_scs")
            self.assertEqual(scs.name, "test_scs")
            self.assertIsInstance(scs.parameters, dict)
            
        except ImportError:
            self.skipTest("SCS module not available")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete hydrological model."""
    
    @unittest.skipIf(not os.path.exists('data/rainfall.csv'), "Test data not available")
    def test_full_model_with_real_data(self):
        """Test full model with real data if available."""
        import pandas as pd
        
        # Load test data
        try:
            rainfall_data = pd.read_csv('data/rainfall.csv')
            pet_data = pd.read_csv('data/pet.csv')
            
            # Create model with real modules
            from hydro_model.runoff import XAJModule
            from hydro_model.routing import UnitHydrographModule
            
            runoff_module = XAJModule(name="xaj_test")
            routing_module = UnitHydrographModule(name="uh_test")
            
            model = HydrologicalModel(
                name="integration_test",
                runoff_module=runoff_module,
                routing_module=routing_module
            )
            
            # Run model
            results = model.run(rainfall_data['rainfall'].values, pet_data['pet'].values)
            
            # Basic checks
            self.assertIsInstance(results, dict)
            self.assertGreater(len(model.outflow_history), 0)
            self.assertTrue(all(flow >= 0 for flow in model.outflow_history))
            
        except (ImportError, FileNotFoundError, KeyError) as e:
            self.skipTest(f"Integration test requirements not met: {e}")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)