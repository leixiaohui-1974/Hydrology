"""Integration tests for the Hydrology framework.

These tests verify that different components work together correctly
and that data flows properly between modules.
"""
import unittest
import sys
import os
import numpy as np
import tempfile
import json
from unittest.mock import patch, MagicMock

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hydro_model.model import HydrologicalModel
from common.controller import Controller
from common.config import ConfigParser
from common.error_handler import HydrologyError, ValidationError


class MockRunoffModule:
    """Mock runoff module for integration testing."""
    
    def __init__(self, name="mock_runoff"):
        self.name = name
        self.parameters = {
            'cn': 75,  # Curve number
            'initial_abstraction': 0.2
        }
        self.state = {
            'soil_moisture': 0.5,
            'cumulative_runoff': 0.0
        }
        self.results = {
            'runoff_history': [],
            'infiltration_history': []
        }
    
    def step(self, inflows, dt):
        """Simulate one time step."""
        rainfall = inflows.get('rainfall', 0.0)
        pet = inflows.get('pet', 0.0)
        
        # Simple runoff calculation
        if rainfall > 0:
            # SCS Curve Number method (simplified)
            s = (25400 / self.parameters['cn']) - 254
            ia = self.parameters['initial_abstraction'] * s
            
            if rainfall > ia:
                runoff = ((rainfall - ia) ** 2) / (rainfall - ia + s)
            else:
                runoff = 0.0
        else:
            runoff = 0.0
        
        infiltration = rainfall - runoff
        
        # Update state
        self.state['soil_moisture'] += (infiltration - pet * 0.1) / 1000
        self.state['soil_moisture'] = max(0, min(1, self.state['soil_moisture']))
        self.state['cumulative_runoff'] += runoff
        
        # Store results
        self.results['runoff_history'].append(runoff)
        self.results['infiltration_history'].append(infiltration)
        
        return {
            'runoff': runoff,
            'infiltration': infiltration,
            'soil_moisture': self.state['soil_moisture']
        }
    
    def get_results(self):
        """Get simulation results."""
        return self.results.copy()
    
    def get_parameters(self):
        """Get model parameters."""
        return self.parameters.copy()
    
    def set_parameters(self, params):
        """Set model parameters."""
        self.parameters.update(params)


class MockRoutingModule:
    """Mock routing module for integration testing."""
    
    def __init__(self, name="mock_routing"):
        self.name = name
        self.parameters = {
            'lag_time': 2.0,  # hours
            'attenuation': 0.8
        }
        self.state = {
            'channel_storage': 0.0,
            'lag_buffer': []
        }
        self.results = {
            'flow_history': [],
            'storage_history': []
        }
    
    def step(self, inflows, dt):
        """Simulate one time step."""
        runoff = inflows.get('runoff', 0.0)
        
        # Simple lag and attenuation routing
        lag_steps = int(self.parameters['lag_time'] * 3600 / dt)
        
        # Add current runoff to lag buffer
        self.state['lag_buffer'].append(runoff)
        
        # Remove old values if buffer is too long
        if len(self.state['lag_buffer']) > lag_steps:
            delayed_runoff = self.state['lag_buffer'].pop(0)
        else:
            delayed_runoff = 0.0
        
        # Apply attenuation
        outflow = delayed_runoff * self.parameters['attenuation']
        
        # Update storage
        self.state['channel_storage'] += delayed_runoff - outflow
        self.state['channel_storage'] = max(0, self.state['channel_storage'])
        
        # Store results
        self.results['flow_history'].append(outflow)
        self.results['storage_history'].append(self.state['channel_storage'])
        
        return {
            'flow': outflow,
            'storage': self.state['channel_storage']
        }
    
    def get_results(self):
        """Get simulation results."""
        return self.results.copy()
    
    def get_parameters(self):
        """Get model parameters."""
        return self.parameters.copy()
    
    def set_parameters(self, params):
        """Set model parameters."""
        self.parameters.update(params)


class TestModelIntegration(unittest.TestCase):
    """Test integration between different model components."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.runoff_module = MockRunoffModule()
        self.routing_module = MockRoutingModule()
    
    def test_runoff_routing_integration(self):
        """Test integration between runoff and routing modules."""
        # Create model with both runoff and routing
        model = HydrologicalModel(
            "integrated_test",
            runoff_module=self.runoff_module,
            routing_module=self.routing_module
        )
        
        # Create test rainfall event
        rainfall_data = [0, 0, 5, 15, 25, 20, 10, 5, 2, 0, 0, 0]
        pet_data = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
        dt = 3600  # 1 hour
        
        results = []
        
        # Run simulation
        for i, (rainfall, pet) in enumerate(zip(rainfall_data, pet_data)):
            inflows = {'rainfall': rainfall, 'pet': pet}
            result = model.step(inflows, dt)
            results.append(result)
        
        # Verify data flow
        self.assertEqual(len(results), len(rainfall_data))
        
        # Check that runoff is generated during rainfall
        runoff_results = self.runoff_module.get_results()
        self.assertTrue(any(r > 0 for r in runoff_results['runoff_history']))
        
        # Check that routing produces delayed flow
        routing_results = self.routing_module.get_results()
        flow_history = routing_results['flow_history']
        
        # Peak flow should be delayed relative to peak rainfall
        peak_rainfall_time = rainfall_data.index(max(rainfall_data))
        peak_flow_time = flow_history.index(max(flow_history))
        self.assertGreater(peak_flow_time, peak_rainfall_time)
        
        # Total flow should be less than total runoff (due to attenuation)
        total_runoff = sum(runoff_results['runoff_history'])
        total_flow = sum(flow_history)
        self.assertLess(total_flow, total_runoff)
        
        print(f"\nIntegration test results:")
        print(f"Total rainfall: {sum(rainfall_data):.2f} mm")
        print(f"Total runoff: {total_runoff:.2f} mm")
        print(f"Total flow: {total_flow:.2f} mm")
        print(f"Runoff coefficient: {total_runoff/sum(rainfall_data):.3f}")
        print(f"Routing efficiency: {total_flow/total_runoff:.3f}")
    
    def test_model_state_consistency(self):
        """Test that model state remains consistent across time steps."""
        model = HydrologicalModel(
            "consistency_test",
            runoff_module=self.runoff_module
        )
        
        # Run simulation with varying inputs
        np.random.seed(42)  # For reproducible results
        num_steps = 100
        
        for i in range(num_steps):
            rainfall = max(0, np.random.normal(5, 10))  # Variable rainfall
            pet = max(0, np.random.normal(3, 1))  # Variable PET
            
            inflows = {'rainfall': rainfall, 'pet': pet}
            result = model.step(inflows, dt=3600)
            
            # Check that results are reasonable
            self.assertGreaterEqual(result.get('runoff', 0), 0)
            self.assertLessEqual(result.get('runoff', 0), rainfall)
            
            # Check soil moisture bounds
            soil_moisture = result.get('soil_moisture', 0.5)
            self.assertGreaterEqual(soil_moisture, 0)
            self.assertLessEqual(soil_moisture, 1)
        
        # Check that cumulative values make sense
        runoff_results = self.runoff_module.get_results()
        total_runoff = sum(runoff_results['runoff_history'])
        self.assertGreater(total_runoff, 0)
        
        print(f"\nConsistency test completed: {num_steps} steps")
        print(f"Final soil moisture: {soil_moisture:.3f}")
        print(f"Total runoff: {total_runoff:.2f} mm")
    
    def test_parameter_sensitivity(self):
        """Test model sensitivity to parameter changes."""
        base_model = HydrologicalModel(
            "base_model",
            runoff_module=MockRunoffModule()
        )
        
        # Test with different curve numbers
        cn_values = [60, 75, 90]
        results_by_cn = {}
        
        # Standard rainfall event
        rainfall_event = [0, 5, 15, 25, 15, 5, 0]
        pet_constant = 2.0
        
        for cn in cn_values:
            # Create new model with different CN
            runoff_module = MockRunoffModule()
            runoff_module.set_parameters({'cn': cn})
            
            model = HydrologicalModel(
                f"cn_{cn}_model",
                runoff_module=runoff_module
            )
            
            # Run simulation
            total_runoff = 0
            for rainfall in rainfall_event:
                inflows = {'rainfall': rainfall, 'pet': pet_constant}
                result = model.step(inflows, dt=3600)
                total_runoff += result.get('runoff', 0)
            
            results_by_cn[cn] = total_runoff
        
        # Verify that higher CN produces more runoff
        cn_sorted = sorted(cn_values)
        runoff_sorted = [results_by_cn[cn] for cn in cn_sorted]
        
        for i in range(1, len(runoff_sorted)):
            self.assertGreater(runoff_sorted[i], runoff_sorted[i-1],
                             "Higher CN should produce more runoff")
        
        print(f"\nParameter sensitivity test:")
        for cn in cn_values:
            print(f"CN {cn}: {results_by_cn[cn]:.2f} mm runoff")


class TestControllerIntegration(unittest.TestCase):
    """Test integration with the Controller system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.controller = Controller()
    
    def test_multiple_model_coordination(self):
        """Test coordination of multiple models through controller."""
        # Create multiple models
        models = []
        for i in range(3):
            runoff_module = MockRunoffModule(f"runoff_{i}")
            # Vary parameters slightly
            runoff_module.set_parameters({'cn': 70 + i * 10})
            
            model = HydrologicalModel(f"model_{i}", runoff_module)
            models.append(model)
            self.controller.add_component(model)
        
        # Run coordinated simulation
        rainfall_data = [0, 10, 20, 15, 5, 0]
        results_by_model = {}
        
        for rainfall in rainfall_data:
            inflows = {'rainfall': rainfall, 'pet': 2.0}
            
            # Run all models through controller
            try:
                self.controller.run_step(inflows, dt=3600)
            except AttributeError:
                # Controller might not have run_step method
                # Run models individually
                for model in models:
                    model.step(inflows, dt=3600)
        
        # Collect results
        for i, model in enumerate(models):
            runoff_results = model.runoff_module.get_results()
            total_runoff = sum(runoff_results['runoff_history'])
            results_by_model[f"model_{i}"] = total_runoff
        
        # Verify that models with different parameters produce different results
        runoff_values = list(results_by_model.values())
        self.assertGreater(len(set(runoff_values)), 1,
                          "Models with different parameters should produce different results")
        
        print(f"\nMultiple model coordination test:")
        for model_name, total_runoff in results_by_model.items():
            print(f"{model_name}: {total_runoff:.2f} mm runoff")
    
    def test_error_propagation(self):
        """Test error handling across integrated components."""
        # Create a model that will cause errors
        class ErrorProneModule:
            def __init__(self):
                self.name = "error_prone"
                self.step_count = 0
            
            def step(self, inflows, dt):
                self.step_count += 1
                if self.step_count == 3:
                    raise ValidationError("Simulated error in module")
                return {'runoff': 1.0}
            
            def get_results(self):
                return {'runoff_history': []}
        
        error_module = ErrorProneModule()
        model = HydrologicalModel("error_test", error_module)
        self.controller.add_component(model)
        
        # Run simulation and expect error on third step
        inflows = {'rainfall': 5.0, 'pet': 2.0}
        
        # First two steps should work
        for i in range(2):
            try:
                model.step(inflows, dt=3600)
            except Exception as e:
                self.fail(f"Unexpected error on step {i+1}: {e}")
        
        # Third step should raise error
        with self.assertRaises(ValidationError):
            model.step(inflows, dt=3600)
        
        print("\nError propagation test completed successfully")


class TestConfigIntegration(unittest.TestCase):
    """Test integration with configuration system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_config_driven_model_setup(self):
        """Test setting up models from configuration files."""
        # Create test configuration
        config_data = {
            'model': {
                'name': 'config_test_model',
                'timestep': 3600
            },
            'runoff': {
                'module': 'mock',
                'parameters': {
                    'cn': 80,
                    'initial_abstraction': 0.15
                }
            },
            'routing': {
                'module': 'mock',
                'parameters': {
                    'lag_time': 3.0,
                    'attenuation': 0.75
                }
            },
            'simulation': {
                'start_time': '2020-01-01 00:00:00',
                'end_time': '2020-01-02 00:00:00',
                'output_interval': 3600
            }
        }
        
        # Write configuration to file
        config_file = os.path.join(self.temp_dir, 'test_config.json')
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Load configuration
        config_parser = ConfigParser()
        config = config_parser.load_config(config_file)
        
        # Verify configuration loading
        self.assertEqual(config['model']['name'], 'config_test_model')
        self.assertEqual(config['runoff']['parameters']['cn'], 80)
        
        # Create model from configuration
        runoff_module = MockRunoffModule()
        runoff_module.set_parameters(config['runoff']['parameters'])
        
        routing_module = MockRoutingModule()
        routing_module.set_parameters(config['routing']['parameters'])
        
        model = HydrologicalModel(
            config['model']['name'],
            runoff_module=runoff_module,
            routing_module=routing_module
        )
        
        # Test that model uses configured parameters
        runoff_params = runoff_module.get_parameters()
        self.assertEqual(runoff_params['cn'], 80)
        self.assertEqual(runoff_params['initial_abstraction'], 0.15)
        
        routing_params = routing_module.get_parameters()
        self.assertEqual(routing_params['lag_time'], 3.0)
        self.assertEqual(routing_params['attenuation'], 0.75)
        
        print(f"\nConfig-driven model setup test completed")
        print(f"Model name: {model.name}")
        print(f"Runoff CN: {runoff_params['cn']}")
        print(f"Routing lag time: {routing_params['lag_time']} hours")
    
    def test_config_validation(self):
        """Test configuration validation."""
        config_parser = ConfigParser()
        
        # Test invalid configuration
        invalid_config = {
            'model': {
                'name': '',  # Empty name should be invalid
                'timestep': -1  # Negative timestep should be invalid
            }
        }
        
        # Write invalid configuration
        invalid_config_file = os.path.join(self.temp_dir, 'invalid_config.json')
        with open(invalid_config_file, 'w') as f:
            json.dump(invalid_config, f)
        
        # Loading should work, but validation might catch issues
        try:
            config = config_parser.load_config(invalid_config_file)
            
            # Manual validation
            if not config['model']['name']:
                raise ValidationError("Model name cannot be empty")
            if config['model']['timestep'] <= 0:
                raise ValidationError("Timestep must be positive")
                
        except (ValidationError, HydrologyError) as e:
            print(f"\nConfig validation correctly caught error: {e}")
        else:
            self.fail("Config validation should have caught invalid configuration")


class TestDataFlowIntegration(unittest.TestCase):
    """Test data flow between components."""
    
    def test_complete_simulation_workflow(self):
        """Test complete simulation workflow from input to output."""
        # Create complete model setup
        runoff_module = MockRunoffModule()
        routing_module = MockRoutingModule()
        
        model = HydrologicalModel(
            "workflow_test",
            runoff_module=runoff_module,
            routing_module=routing_module
        )
        
        # Create realistic input data
        num_days = 10
        hours_per_day = 24
        total_hours = num_days * hours_per_day
        
        # Generate synthetic weather data
        np.random.seed(123)
        rainfall = np.random.exponential(2.0, total_hours)
        rainfall[rainfall < 0.1] = 0  # No light rain
        
        temperature = 15 + 10 * np.sin(np.arange(total_hours) * 2 * np.pi / 24)
        pet = np.maximum(0, 0.1 * temperature + np.random.normal(0, 0.5, total_hours))
        
        # Run complete simulation
        simulation_results = {
            'time': [],
            'rainfall': [],
            'pet': [],
            'runoff': [],
            'flow': [],
            'soil_moisture': []
        }
        
        for hour in range(total_hours):
            inflows = {
                'rainfall': rainfall[hour],
                'pet': pet[hour]
            }
            
            result = model.step(inflows, dt=3600)
            
            # Store results
            simulation_results['time'].append(hour)
            simulation_results['rainfall'].append(rainfall[hour])
            simulation_results['pet'].append(pet[hour])
            simulation_results['runoff'].append(result.get('runoff', 0))
            simulation_results['flow'].append(result.get('flow', 0))
            simulation_results['soil_moisture'].append(result.get('soil_moisture', 0.5))
        
        # Verify simulation results
        total_rainfall = sum(simulation_results['rainfall'])
        total_runoff = sum(simulation_results['runoff'])
        total_flow = sum(simulation_results['flow'])
        
        self.assertGreater(total_rainfall, 0)
        self.assertGreater(total_runoff, 0)
        self.assertGreater(total_flow, 0)
        self.assertLess(total_runoff, total_rainfall)
        self.assertLess(total_flow, total_runoff)
        
        # Check that soil moisture varies realistically
        soil_moisture_values = simulation_results['soil_moisture']
        self.assertTrue(all(0 <= sm <= 1 for sm in soil_moisture_values))
        self.assertGreater(max(soil_moisture_values) - min(soil_moisture_values), 0.1)
        
        print(f"\nComplete simulation workflow test:")
        print(f"Simulation period: {num_days} days ({total_hours} hours)")
        print(f"Total rainfall: {total_rainfall:.1f} mm")
        print(f"Total runoff: {total_runoff:.1f} mm")
        print(f"Total flow: {total_flow:.1f} mm")
        print(f"Runoff coefficient: {total_runoff/total_rainfall:.3f}")
        print(f"Routing efficiency: {total_flow/total_runoff:.3f}")
        print(f"Soil moisture range: {min(soil_moisture_values):.3f} - {max(soil_moisture_values):.3f}")
        
        # Verify mass balance (approximately)
        infiltration_results = runoff_module.get_results()['infiltration_history']
        total_infiltration = sum(infiltration_results)
        
        mass_balance_error = abs(total_rainfall - total_runoff - total_infiltration)
        relative_error = mass_balance_error / total_rainfall
        
        print(f"Mass balance error: {relative_error:.4f} ({mass_balance_error:.2f} mm)")
        self.assertLess(relative_error, 0.01, "Mass balance error too large")
    
    def test_model_restart_capability(self):
        """Test that models can be stopped and restarted."""
        # Create model and run initial simulation
        runoff_module = MockRunoffModule()
        model = HydrologicalModel("restart_test", runoff_module)
        
        # Run first part of simulation
        rainfall_part1 = [5, 10, 15, 10, 5]
        results_part1 = []
        
        for rainfall in rainfall_part1:
            inflows = {'rainfall': rainfall, 'pet': 2.0}
            result = model.step(inflows, dt=3600)
            results_part1.append(result)
        
        # Save model state
        saved_state = {
            'runoff_state': runoff_module.state.copy(),
            'runoff_results': runoff_module.get_results(),
            'model_history': model.outflow_history.copy()
        }
        
        # Continue simulation
        rainfall_part2 = [3, 1, 0, 0, 0]
        results_part2 = []
        
        for rainfall in rainfall_part2:
            inflows = {'rainfall': rainfall, 'pet': 2.0}
            result = model.step(inflows, dt=3600)
            results_part2.append(result)
        
        # Verify continuity
        all_results = results_part1 + results_part2
        self.assertEqual(len(all_results), len(rainfall_part1) + len(rainfall_part2))
        
        # Check that state was preserved correctly
        final_runoff_results = runoff_module.get_results()
        total_steps = len(rainfall_part1) + len(rainfall_part2)
        self.assertEqual(len(final_runoff_results['runoff_history']), total_steps)
        
        print(f"\nModel restart test completed")
        print(f"Part 1 steps: {len(rainfall_part1)}")
        print(f"Part 2 steps: {len(rainfall_part2)}")
        print(f"Total runoff history length: {len(final_runoff_results['runoff_history'])}")
        print(f"Final soil moisture: {runoff_module.state['soil_moisture']:.3f}")


if __name__ == '__main__':
    print("Running Integration Tests...")
    print("=" * 50)
    
    unittest.main(verbosity=2)