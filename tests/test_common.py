"""Tests for the common module components."""
import unittest
import sys
import os
import tempfile
import yaml
import json
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.config_parser import ConfigParser
from common.error_handler import (
    HydrologyError, ConfigurationError, ModelError, DataError,
    ValidationError, handle_errors, log_error, validate_input
)
from common.base_model import BaseModelComponent
from common.controller import Controller


class TestConfigParser(unittest.TestCase):
    """Test cases for ConfigParser class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = ConfigParser()
        
        # Sample configuration data
        self.sample_config = {
            'simulation': {
                'name': 'test_simulation',
                'start_time': '2023-01-01',
                'end_time': '2023-12-31',
                'time_step': 3600
            },
            'models': {
                'hydro_model': {
                    'type': 'XAJModule',
                    'name': 'test_xaj',
                    'parameters': {
                        'K': 0.5,
                        'B': 0.3,
                        'IM': 0.01
                    }
                },
                'routing_model': {
                    'type': 'UnitHydrographModule',
                    'name': 'test_uh',
                    'parameters': {
                        'lag_time': 2.0
                    }
                }
            },
            'data': {
                'rainfall': 'data/rainfall.csv',
                'pet': 'data/pet.csv'
            }
        }
    
    def test_load_yaml_config(self):
        """Test loading YAML configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.sample_config, f)
            temp_file = f.name
        
        try:
            config = self.parser.load_config(temp_file)
            self.assertEqual(config['simulation']['name'], 'test_simulation')
            self.assertEqual(config['models']['hydro_model']['type'], 'XAJModule')
        finally:
            os.unlink(temp_file)
    
    def test_load_json_config(self):
        """Test loading JSON configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config, f)
            temp_file = f.name
        
        try:
            config = self.parser.load_config(temp_file)
            self.assertEqual(config['simulation']['name'], 'test_simulation')
            self.assertEqual(config['models']['hydro_model']['type'], 'XAJModule')
        finally:
            os.unlink(temp_file)
    
    def test_load_nonexistent_file(self):
        """Test loading non-existent configuration file."""
        with self.assertRaises(ConfigurationError):
            self.parser.load_config('nonexistent_file.yaml')
    
    def test_load_invalid_yaml(self):
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('invalid: yaml: content: [unclosed')
            temp_file = f.name
        
        try:
            with self.assertRaises(ConfigurationError):
                self.parser.load_config(temp_file)
        finally:
            os.unlink(temp_file)
    
    def test_validate_config_structure(self):
        """Test configuration structure validation."""
        # Valid configuration
        self.assertTrue(self.parser.validate_config(self.sample_config))
        
        # Missing required sections
        invalid_config = {'simulation': {'name': 'test'}}
        with self.assertRaises(ConfigurationError):
            self.parser.validate_config(invalid_config)
    
    def test_get_model_config(self):
        """Test extracting model configuration."""
        model_config = self.parser.get_model_config(self.sample_config, 'hydro_model')
        
        self.assertEqual(model_config['type'], 'XAJModule')
        self.assertEqual(model_config['name'], 'test_xaj')
        self.assertEqual(model_config['parameters']['K'], 0.5)
    
    def test_get_nonexistent_model_config(self):
        """Test extracting non-existent model configuration."""
        with self.assertRaises(ConfigurationError):
            self.parser.get_model_config(self.sample_config, 'nonexistent_model')
    
    def test_substitute_variables(self):
        """Test variable substitution in configuration."""
        config_with_vars = {
            'base_path': '/data',
            'files': {
                'rainfall': '${base_path}/rainfall.csv',
                'pet': '${base_path}/pet.csv'
            }
        }
        
        resolved_config = self.parser.substitute_variables(config_with_vars)
        self.assertEqual(resolved_config['files']['rainfall'], '/data/rainfall.csv')
        self.assertEqual(resolved_config['files']['pet'], '/data/pet.csv')
    
    def test_merge_configs(self):
        """Test merging multiple configurations."""
        base_config = {
            'simulation': {'name': 'base', 'time_step': 3600},
            'models': {'hydro_model': {'type': 'XAJ'}}
        }
        
        override_config = {
            'simulation': {'name': 'override'},
            'models': {'routing_model': {'type': 'UH'}}
        }
        
        merged = self.parser.merge_configs(base_config, override_config)
        
        self.assertEqual(merged['simulation']['name'], 'override')
        self.assertEqual(merged['simulation']['time_step'], 3600)
        self.assertEqual(merged['models']['hydro_model']['type'], 'XAJ')
        self.assertEqual(merged['models']['routing_model']['type'], 'UH')


class TestErrorHandler(unittest.TestCase):
    """Test cases for error handling functionality."""
    
    def test_custom_exceptions(self):
        """Test custom exception classes."""
        # Test HydrologyError
        with self.assertRaises(HydrologyError):
            raise HydrologyError("Test hydrology error")
        
        # Test ConfigurationError
        with self.assertRaises(ConfigurationError):
            raise ConfigurationError("Test configuration error")
        
        # Test ModelError
        with self.assertRaises(ModelError):
            raise ModelError("Test model error")
        
        # Test DataError
        with self.assertRaises(DataError):
            raise DataError("Test data error")
        
        # Test ValidationError
        with self.assertRaises(ValidationError):
            raise ValidationError("Test validation error")
    
    def test_exception_inheritance(self):
        """Test that custom exceptions inherit properly."""
        self.assertTrue(issubclass(ConfigurationError, HydrologyError))
        self.assertTrue(issubclass(ModelError, HydrologyError))
        self.assertTrue(issubclass(DataError, HydrologyError))
        self.assertTrue(issubclass(ValidationError, HydrologyError))
    
    @patch('common.error_handler.logging')
    def test_log_error(self, mock_logging):
        """Test error logging functionality."""
        test_error = ValueError("Test error message")
        
        log_error(test_error, "test_context")
        
        # Verify logging was called
        mock_logging.error.assert_called()
        call_args = mock_logging.error.call_args[0][0]
        self.assertIn("test_context", call_args)
        self.assertIn("Test error message", call_args)
    
    def test_handle_errors_decorator(self):
        """Test the handle_errors decorator."""
        
        @handle_errors("test_function")
        def test_function_success():
            return "success"
        
        @handle_errors("test_function")
        def test_function_error():
            raise ValueError("Test error")
        
        # Test successful execution
        result = test_function_success()
        self.assertEqual(result, "success")
        
        # Test error handling
        with self.assertRaises(HydrologyError):
            test_function_error()
    
    def test_validate_input_decorator(self):
        """Test the validate_input decorator."""
        
        @validate_input
        def test_function(x, y=None):
            if x is None:
                raise ValueError("x cannot be None")
            if y is not None and y < 0:
                raise ValueError("y must be non-negative")
            return x + (y or 0)
        
        # Test valid inputs
        result = test_function(5, 3)
        self.assertEqual(result, 8)
        
        # Test invalid inputs
        with self.assertRaises(ValidationError):
            test_function(None)
        
        with self.assertRaises(ValidationError):
            test_function(5, -1)
    
    def test_error_context_manager(self):
        """Test error handling in context manager."""
        from common.error_handler import error_context
        
        # Test successful execution
        with error_context("test_operation"):
            result = 2 + 2
        
        self.assertEqual(result, 4)
        
        # Test error handling
        with self.assertRaises(HydrologyError):
            with error_context("test_operation"):
                raise ValueError("Test error")


class TestBaseModelComponent(unittest.TestCase):
    """Test cases for BaseModelComponent class."""
    
    def test_abstract_methods(self):
        """Test that BaseModelComponent is abstract."""
        # Should not be able to instantiate directly
        with self.assertRaises(TypeError):
            BaseModelComponent("test")
    
    def test_concrete_implementation(self):
        """Test concrete implementation of BaseModelComponent."""
        
        class ConcreteModel(BaseModelComponent):
            def step(self, inflows, dt):
                return {'output': sum(inflows.values())}
            
            def get_results(self):
                return {'test_results': [1, 2, 3]}
        
        model = ConcreteModel("test_model")
        self.assertEqual(model.name, "test_model")
        
        # Test step method
        result = model.step({'input1': 5, 'input2': 3}, 1.0)
        self.assertEqual(result['output'], 8)
        
        # Test get_results method
        results = model.get_results()
        self.assertEqual(results['test_results'], [1, 2, 3])
    
    def test_name_property(self):
        """Test name property functionality."""
        
        class TestModel(BaseModelComponent):
            def step(self, inflows, dt):
                return {}
            
            def get_results(self):
                return {}
        
        model = TestModel("test_name")
        self.assertEqual(model.name, "test_name")
        
        # Test name validation
        with self.assertRaises(ValueError):
            TestModel("")  # Empty name
        
        with self.assertRaises(TypeError):
            TestModel(123)  # Non-string name


class TestController(unittest.TestCase):
    """Test cases for Controller class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.controller = Controller()
    
    def test_add_component(self):
        """Test adding components to controller."""
        
        class MockComponent(BaseModelComponent):
            def step(self, inflows, dt):
                return {'output': 1}
            
            def get_results(self):
                return {'results': []}
        
        component = MockComponent("test_component")
        self.controller.add_component(component)
        
        self.assertIn("test_component", self.controller.components)
        self.assertEqual(self.controller.components["test_component"], component)
    
    def test_add_duplicate_component(self):
        """Test adding component with duplicate name."""
        
        class MockComponent(BaseModelComponent):
            def step(self, inflows, dt):
                return {}
            
            def get_results(self):
                return {}
        
        component1 = MockComponent("duplicate_name")
        component2 = MockComponent("duplicate_name")
        
        self.controller.add_component(component1)
        
        with self.assertRaises(ValueError):
            self.controller.add_component(component2)
    
    def test_remove_component(self):
        """Test removing components from controller."""
        
        class MockComponent(BaseModelComponent):
            def step(self, inflows, dt):
                return {}
            
            def get_results(self):
                return {}
        
        component = MockComponent("test_component")
        self.controller.add_component(component)
        
        # Verify component was added
        self.assertIn("test_component", self.controller.components)
        
        # Remove component
        self.controller.remove_component("test_component")
        
        # Verify component was removed
        self.assertNotIn("test_component", self.controller.components)
    
    def test_remove_nonexistent_component(self):
        """Test removing non-existent component."""
        with self.assertRaises(KeyError):
            self.controller.remove_component("nonexistent_component")
    
    def test_get_component(self):
        """Test getting component by name."""
        
        class MockComponent(BaseModelComponent):
            def step(self, inflows, dt):
                return {}
            
            def get_results(self):
                return {}
        
        component = MockComponent("test_component")
        self.controller.add_component(component)
        
        retrieved = self.controller.get_component("test_component")
        self.assertEqual(retrieved, component)
    
    def test_get_nonexistent_component(self):
        """Test getting non-existent component."""
        with self.assertRaises(KeyError):
            self.controller.get_component("nonexistent_component")
    
    @patch('common.error_handler.log_error')
    def test_run_simulation_with_errors(self, mock_log_error):
        """Test simulation run with component errors."""
        
        class ErrorComponent(BaseModelComponent):
            def step(self, inflows, dt):
                raise RuntimeError("Component error")
            
            def get_results(self):
                return {}
        
        error_component = ErrorComponent("error_component")
        self.controller.add_component(error_component)
        
        # Should handle errors gracefully
        with self.assertRaises(ModelError):
            self.controller.run_step({}, 1.0)
        
        # Verify error was logged
        mock_log_error.assert_called()


class TestIntegrationCommon(unittest.TestCase):
    """Integration tests for common module components."""
    
    def test_config_parser_with_error_handling(self):
        """Test config parser with error handling integration."""
        parser = ConfigParser()
        
        # Test with invalid file - should raise ConfigurationError
        with self.assertRaises(ConfigurationError):
            parser.load_config("nonexistent.yaml")
    
    def test_controller_with_config_parser(self):
        """Test controller integration with config parser."""
        # Create a temporary config file
        config_data = {
            'simulation': {
                'name': 'integration_test',
                'time_step': 3600
            },
            'models': {
                'test_model': {
                    'type': 'MockModel',
                    'parameters': {'param1': 1.0}
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_file = f.name
        
        try:
            parser = ConfigParser()
            config = parser.load_config(temp_file)
            
            # Verify config was loaded correctly
            self.assertEqual(config['simulation']['name'], 'integration_test')
            self.assertEqual(config['models']['test_model']['type'], 'MockModel')
            
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)