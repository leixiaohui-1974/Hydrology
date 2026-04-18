# PySWMM-like Interface for Hydro-Suite

This document describes the new high-level, `pyswmm`-like interface for the Hydro-Suite modeling framework. This API is designed to provide a more intuitive and interactive way to run simulations, inspect results, and implement runtime control logic, which is especially useful for research, development, and complex control strategy testing.

## Overview

The standard way to run a simulation in this framework is via a command-line script that executes the entire simulation from start to finish based on a YAML configuration file (e.g., `run_from_config.py`). This is efficient for batch runs but lacks interactivity.

The new `pyswmm`-like interface provides a solution by wrapping the core simulation engine in a `Simulation` object that can be controlled step-by-step, similar to the popular `pyswmm` library.

### Key Features

- **Step-by-Step Execution**: Iterate through a simulation one time step at a time using a simple `for` loop.
- **Real-time Data Access**: Read results from any model component (e.g., flow in a link, depth at a node) within the simulation loop.
- **Runtime Control**: Modify model parameters (e.g., gate openings, pump status) on the fly based on simulation results.
- **Familiar API**: The interface is intentionally similar to `pyswmm`, making it easy to learn for users with experience in that library.

## How to Use the Interface

The new interface is demonstrated in the `examples/run_pyswmm_style_example.py` script. Here is a breakdown of how it works.

### 1. Import the `Simulation` Class

First, import the main `Simulation` class from the wrapper module.

```python
from pyswmm_wrapper.simulation import Simulation
```

### 2. Initialize the Simulation

Create an instance of the `Simulation` class, passing the path to your YAML configuration file. This is best done using a `with` statement, which automatically handles the setup and cleanup of the simulation context.

```python
config_file = "examples/hydraulic_features_example/config.yaml"

with Simulation(config_file) as sim:
    # Your simulation logic goes here
    ...
```

### 3. Accessing Model Components

Once the `Simulation` object (`sim`) is created, you can access different categories of model components via accessor objects:

- `sim.subcatchments`: Accesses all `HydrologicalModel` components.
- `sim.nodes`: Accesses all `Junction` components.
- `sim.links`: Accesses all other components, such as `HydraulicModel`.

These accessors behave like dictionaries, allowing you to get a specific component by its name as defined in the YAML file.

```python
# Inside the 'with' block:
river_link = sim.links["MyRiver"]
# You can also access nodes and subcatchments if they exist in the config
# e.g., some_node = sim.nodes["J1"]
```

### 4. Iterating Through the Simulation

The `Simulation` object is an iterator. You can step through the simulation from the start time to the end time using a `for` loop. The simulation advances one time step per iteration.

```python
for step in sim:
    # This loop will run for `num_steps` as defined in the config file.
    # The `step` variable itself is not used, but the loop advances the model.
    ...
```

### 5. Reading Results and Applying Control

Inside the loop, you can access the properties of the component wrappers you retrieved earlier. These properties will give you the results from the most recently completed time step.

You can then use these results to implement control logic by setting the properties of other components.

```python
# Full example loop
for step in sim:
    # 1. Read results from the current time step
    current_flow = river_link.flow
    current_gate_opening = river_link.target_setting

    # Print the current state
    print(f"{sim.current_time}\t{current_flow:.2f}\t\t{current_gate_opening:.2f}")

    # 2. Apply runtime control logic
    if current_flow > 20.0:
        # If flow is high, close the gate partially
        river_link.target_setting = 0.5
    else:
        # If flow is normal, keep the gate open
        river_link.target_setting = 1.0
```

This example demonstrates a simple feedback control loop: the flow in the river is monitored, and the opening of a gate within that river reach is adjusted accordingly. This powerful, interactive approach to modeling is the primary benefit of using the new `pyswmm`-like interface.
