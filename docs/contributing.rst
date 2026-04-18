Contributing to Hydrology Framework
====================================

We welcome contributions to the Hydrology Framework! This guide will help you get started with contributing to the project.

.. contents::
   :local:
   :depth: 2

Getting Started
---------------

Development Environment Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Fork and Clone the Repository**::

    git clone https://github.com/your-username/hydrology-framework.git
    cd hydrology-framework

2. **Create a Virtual Environment**::

    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On Linux/Mac
    source venv/bin/activate

3. **Install Development Dependencies**::

    pip install -e .[dev]
    # or
    pip install -r requirements-dev.txt

4. **Install Pre-commit Hooks**::

    pre-commit install

5. **Verify Installation**::

    python -m pytest tests/
    python -c "import hydrology_framework; print('Installation successful!')"

Development Workflow
~~~~~~~~~~~~~~~~~~~~

1. **Create a Feature Branch**::

    git checkout -b feature/your-feature-name

2. **Make Your Changes**
   - Follow the coding standards (see below)
   - Add tests for new functionality
   - Update documentation as needed

3. **Run Tests and Quality Checks**::

    # Run all tests
    python -m pytest
    
    # Run with coverage
    python -m pytest --cov=hydrology_framework --cov-report=html
    
    # Code formatting
    black .
    isort .
    
    # Linting
    flake8 .
    pylint hydrology_framework/
    
    # Type checking
    mypy hydrology_framework/

4. **Commit Your Changes**::

    git add .
    git commit -m "feat: add new feature description"

5. **Push and Create Pull Request**::

    git push origin feature/your-feature-name

Coding Standards
----------------

Code Style
~~~~~~~~~~

We follow PEP 8 with some modifications:

- **Line Length**: Maximum 88 characters (Black default)
- **Imports**: Use isort for import organization
- **Docstrings**: Use Google-style docstrings
- **Type Hints**: Required for all public functions and methods

Example of well-formatted code::

    from typing import Dict, List, Optional, Union
    import numpy as np
    import pandas as pd
    
    from hydrology_framework.common.base_model import BaseModelComponent
    
    
    class ExampleModel(BaseModelComponent):
        """Example model demonstrating coding standards.
        
        This class shows how to properly format code according to our standards.
        
        Args:
            name: The name of the model component.
            parameters: Dictionary of model parameters.
            initial_conditions: Optional initial conditions.
            
        Attributes:
            name: The model name.
            parameters: Model parameters dictionary.
            state: Current model state.
        """
        
        def __init__(
            self,
            name: str,
            parameters: Dict[str, Union[float, int]],
            initial_conditions: Optional[Dict[str, float]] = None,
        ) -> None:
            super().__init__(name)
            self.parameters = parameters
            self.state = initial_conditions or {}
            self._validate_parameters()
            
        def step(
            self, 
            inputs: Dict[str, float], 
            dt: float
        ) -> Dict[str, float]:
            """Execute one simulation time step.
            
            Args:
                inputs: Input values for this time step.
                dt: Time step size in seconds.
                
            Returns:
                Dictionary containing output values.
                
            Raises:
                ValueError: If inputs are invalid.
            """
            self._validate_inputs(inputs)
            
            # Perform calculations
            output = self._calculate_output(inputs, dt)
            
            # Update state
            self._update_state(output, dt)
            
            return output
            
        def _validate_parameters(self) -> None:
            """Validate model parameters.
            
            Raises:
                ValueError: If parameters are invalid.
            """
            required_params = ["param1", "param2"]
            for param in required_params:
                if param not in self.parameters:
                    raise ValueError(f"Missing required parameter: {param}")
                    
        def _validate_inputs(self, inputs: Dict[str, float]) -> None:
            """Validate input values.
            
            Args:
                inputs: Input dictionary to validate.
                
            Raises:
                ValueError: If inputs are invalid.
            """
            if not inputs:
                raise ValueError("Inputs cannot be empty")
                
        def _calculate_output(
            self, 
            inputs: Dict[str, float], 
            dt: float
        ) -> Dict[str, float]:
            """Calculate model output.
            
            Args:
                inputs: Input values.
                dt: Time step size.
                
            Returns:
                Calculated output values.
            """
            # Implementation here
            return {"output": 0.0}
            
        def _update_state(
            self, 
            output: Dict[str, float], 
            dt: float
        ) -> None:
            """Update internal model state.
            
            Args:
                output: Output values from current step.
                dt: Time step size.
            """
            # Update state implementation
            pass

Documentation Standards
~~~~~~~~~~~~~~~~~~~~~~~

- **Docstrings**: All public functions, classes, and methods must have docstrings
- **Type Hints**: Use type hints for all function parameters and return values
- **Comments**: Use comments sparingly, prefer self-documenting code
- **README**: Update README.md if adding new features

Testing Guidelines
------------------

Test Structure
~~~~~~~~~~~~~~

Tests are organized in the ``tests/`` directory::

    tests/
    ├── unit/
    │   ├── test_common/
    │   ├── test_hydro_model/
    │   ├── test_preissmann_model/
    │   ├── test_model_2d/
    │   ├── test_dl_model/
    │   └── test_preprocessing/
    ├── integration/
    │   ├── test_model_coupling/
    │   ├── test_data_flow/
    │   └── test_performance/
    ├── fixtures/
    │   ├── sample_data/
    │   └── test_configs/
    └── conftest.py

Writing Tests
~~~~~~~~~~~~~

Use pytest for all tests. Example test structure::

    import pytest
    import numpy as np
    from unittest.mock import Mock, patch
    
    from hydrology_framework.hydro_model.runoff import SCSCurveNumberModule
    
    
    class TestSCSCurveNumberModule:
        """Test suite for SCS Curve Number Module."""
        
        @pytest.fixture
        def runoff_module(self):
            """Create a test runoff module."""
            return SCSCurveNumberModule(
                curve_number=75,
                area_km2=10.0,
                initial_abstraction_ratio=0.2
            )
            
        def test_initialization(self, runoff_module):
            """Test proper initialization."""
            assert runoff_module.curve_number == 75
            assert runoff_module.area_km2 == 10.0
            assert runoff_module.initial_abstraction_ratio == 0.2
            
        def test_invalid_curve_number(self):
            """Test validation of curve number."""
            with pytest.raises(ValueError, match="Curve number must be"):
                SCSCurveNumberModule(curve_number=150, area_km2=10.0)
                
        def test_runoff_calculation(self, runoff_module):
            """Test runoff calculation."""
            # Test with no rainfall
            runoff = runoff_module.run(rainfall=0.0, dt=3600)
            assert runoff == 0.0
            
            # Test with light rainfall
            runoff = runoff_module.run(rainfall=5.0, dt=3600)
            assert runoff >= 0.0
            
            # Test with heavy rainfall
            runoff = runoff_module.run(rainfall=50.0, dt=3600)
            assert runoff > 0.0
            
        def test_state_persistence(self, runoff_module):
            """Test that state is properly maintained."""
            # First rainfall event
            runoff1 = runoff_module.run(rainfall=20.0, dt=3600)
            
            # Second rainfall event (should consider antecedent conditions)
            runoff2 = runoff_module.run(rainfall=20.0, dt=3600)
            
            # Results should be different due to state
            assert runoff1 != runoff2
            
        @pytest.mark.parametrize("rainfall,expected_range", [
            (0.0, (0.0, 0.0)),
            (10.0, (0.0, 5.0)),
            (30.0, (5.0, 20.0)),
            (100.0, (50.0, 200.0)),
        ])
        def test_runoff_ranges(self, runoff_module, rainfall, expected_range):
            """Test runoff is within expected ranges."""
            runoff = runoff_module.run(rainfall=rainfall, dt=3600)
            assert expected_range[0] <= runoff <= expected_range[1]
            
        def test_performance(self, runoff_module):
            """Test performance with large datasets."""
            import time
            
            rainfall_data = np.random.exponential(5.0, 1000)
            
            start_time = time.time()
            for rainfall in rainfall_data:
                runoff_module.run(rainfall=rainfall, dt=3600)
            execution_time = time.time() - start_time
            
            # Should process 1000 time steps in less than 1 second
            assert execution_time < 1.0
            
        @patch('hydrology_framework.hydro_model.runoff.logger')
        def test_logging(self, mock_logger, runoff_module):
            """Test that appropriate logging occurs."""
            runoff_module.run(rainfall=100.0, dt=3600)
            mock_logger.debug.assert_called()

Integration Tests
~~~~~~~~~~~~~~~~~

Integration tests verify that components work together::

    import pytest
    from hydrology_framework.common.controller import SimulationController
    from hydrology_framework.hydro_model.runoff import SCSCurveNumberModule
    from hydrology_framework.hydro_model.routing import SimpleRouting
    
    
    class TestModelIntegration:
        """Test integration between different model components."""
        
        @pytest.fixture
        def controller(self):
            """Create a simulation controller with test components."""
            controller = SimulationController()
            
            # Add runoff module
            runoff = SCSCurveNumberModule(
                curve_number=75, area_km2=10.0
            )
            controller.add_component(runoff)
            
            # Add routing module
            routing = SimpleRouting(k_q=0.5, k_s=0.1)
            controller.add_component(routing)
            
            # Connect components
            controller.add_connection("runoff", "routing")
            
            return controller
            
        def test_coupled_simulation(self, controller):
            """Test coupled runoff-routing simulation."""
            # Run simulation for 24 hours
            results = []
            for hour in range(24):
                inputs = {"runoff": {"rainfall": 5.0 if hour < 6 else 0.0}}
                controller.step(inputs, dt=3600)
                
                result = controller.get_results()
                results.append(result)
                
            # Verify results
            assert len(results) == 24
            assert all("runoff" in r and "routing" in r for r in results)

Contribution Types
------------------

Bug Reports
~~~~~~~~~~~

When reporting bugs, please include:

- **Environment**: Python version, OS, package versions
- **Reproduction Steps**: Minimal code to reproduce the issue
- **Expected Behavior**: What should happen
- **Actual Behavior**: What actually happens
- **Error Messages**: Full error traceback if applicable

Example bug report template::

    **Environment:**
    - Python: 3.9.7
    - OS: Windows 10
    - hydrology-framework: 1.0.0
    - numpy: 1.21.0
    
    **Bug Description:**
    SCS Curve Number module produces negative runoff values.
    
    **Reproduction Code:**
    ```python
    from hydrology_framework.hydro_model.runoff import SCSCurveNumberModule
    
    module = SCSCurveNumberModule(curve_number=30, area_km2=1.0)
    result = module.run(rainfall=1.0, dt=3600)
    print(f"Runoff: {result}")  # Prints negative value
    ```
    
    **Expected:** Runoff should be >= 0
    **Actual:** Runoff = -0.5

Feature Requests
~~~~~~~~~~~~~~~~

For new features, please provide:

- **Use Case**: Why is this feature needed?
- **Proposed API**: How should the feature work?
- **Implementation Ideas**: Any thoughts on implementation
- **Alternatives**: Other ways to achieve the same goal

Documentation Improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~

Documentation contributions are highly valued:

- **API Documentation**: Improve docstrings and type hints
- **Tutorials**: Add new examples and use cases
- **User Guide**: Improve installation and usage instructions
- **Developer Guide**: Enhance contribution guidelines

Code Contributions
~~~~~~~~~~~~~~~~~~

Types of code contributions:

- **Bug Fixes**: Fix reported issues
- **New Features**: Add new model components or functionality
- **Performance Improvements**: Optimize existing code
- **Test Coverage**: Add tests for untested code
- **Code Quality**: Improve code structure and readability

Review Process
--------------

Pull Request Guidelines
~~~~~~~~~~~~~~~~~~~~~~~

1. **Title**: Use conventional commit format (feat:, fix:, docs:, etc.)
2. **Description**: Clearly describe what the PR does and why
3. **Tests**: Include tests for new functionality
4. **Documentation**: Update docs if needed
5. **Changelog**: Add entry to CHANGELOG.md

PR Template::

    ## Description
    Brief description of changes
    
    ## Type of Change
    - [ ] Bug fix
    - [ ] New feature
    - [ ] Documentation update
    - [ ] Performance improvement
    - [ ] Code refactoring
    
    ## Testing
    - [ ] All existing tests pass
    - [ ] New tests added for new functionality
    - [ ] Manual testing completed
    
    ## Documentation
    - [ ] Docstrings updated
    - [ ] README updated (if needed)
    - [ ] API documentation updated
    
    ## Checklist
    - [ ] Code follows style guidelines
    - [ ] Self-review completed
    - [ ] No breaking changes (or clearly documented)
    - [ ] CHANGELOG.md updated

Review Criteria
~~~~~~~~~~~~~~~

Reviewers will check:

- **Functionality**: Does the code work as intended?
- **Tests**: Are there adequate tests?
- **Documentation**: Is the code well-documented?
- **Style**: Does it follow coding standards?
- **Performance**: Are there any performance concerns?
- **Security**: Are there any security implications?
- **Compatibility**: Does it maintain backward compatibility?

Community Guidelines
--------------------

Code of Conduct
~~~~~~~~~~~~~~~

We are committed to providing a welcoming and inclusive environment:

- **Be Respectful**: Treat everyone with respect and kindness
- **Be Collaborative**: Work together constructively
- **Be Patient**: Help newcomers learn and grow
- **Be Inclusive**: Welcome people of all backgrounds

Communication Channels
~~~~~~~~~~~~~~~~~~~~~~

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and discussions
- **Pull Requests**: Code review and collaboration
- **Documentation**: In-code documentation and guides

Recognition
~~~~~~~~~~~

Contributors are recognized in:

- **CONTRIBUTORS.md**: List of all contributors
- **Release Notes**: Major contributions highlighted
- **Documentation**: Author attribution where appropriate

Getting Help
------------

If you need help with contributing:

1. **Check Documentation**: Read this guide and API docs
2. **Search Issues**: Look for similar questions or problems
3. **Ask Questions**: Open a GitHub Discussion
4. **Join Community**: Participate in project discussions

Thank you for contributing to the Hydrology Framework! Your contributions help make this project better for everyone.