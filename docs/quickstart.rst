Quick Start Guide
=================

This guide will help you get started with the Hydrology Framework quickly.

Basic Concepts
--------------

The Hydrology Framework is built around several key concepts:

* **Components**: Modular building blocks (models, junctions, etc.)
* **Controller**: Orchestrates the simulation
* **Models**: Different types of hydrological models (1D, 2D, ML)
* **Configuration**: JSON/YAML files that define the simulation setup

Your First Simulation
---------------------

Let's create a simple simulation with a basic runoff model.

1. Create a Configuration File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a file called ``simple_config.json``::

    {
        "simulation": {
            "name": "Simple Runoff Simulation",
            "start_time": "2024-01-01T00:00:00",
            "end_time": "2024-01-02T00:00:00",
            "time_step": 3600
        },
        "components": [
            {
                "type": "SimpleRunoffModule",
                "name": "catchment1",
                "parameters": {
                    "area": 100.0,
                    "cn": 75
                }
            }
        ],
        "connections": []
    }

2. Run the Simulation
~~~~~~~~~~~~~~~~~~~~~

Create a Python script ``run_simulation.py``::

    from common.config_parser import ConfigParser
    from common.controller import SimulationController
    import numpy as np
    
    # Load configuration
    config_parser = ConfigParser("simple_config.json")
    controller = config_parser.build_controller()
    
    # Prepare input data (rainfall time series)
    rainfall_data = np.array([10.0, 5.0, 0.0, 0.0])  # mm/hour
    
    # Run simulation
    results = []
    for i, rainfall in enumerate(rainfall_data):
        # Set rainfall input
        inputs = {"catchment1": {"rainfall": rainfall}}
        
        # Step simulation
        controller.step(inputs, dt=3600)  # 1 hour time step
        
        # Collect results
        outflow = controller.get_component("catchment1").get_outflow()
        results.append(outflow)
        
        print(f"Hour {i+1}: Rainfall={rainfall} mm/h, Outflow={outflow:.2f} m³/s")
    
    print("Simulation completed!")

3. Run the Script
~~~~~~~~~~~~~~~~~

::

    python run_simulation.py

Expected output::

    Hour 1: Rainfall=10.0 mm/h, Outflow=2.78 m³/s
    Hour 2: Rainfall=5.0 mm/h, Outflow=1.39 m³/s
    Hour 3: Rainfall=0.0 mm/h, Outflow=0.00 m³/s
    Hour 4: Rainfall=0.0 mm/h, Outflow=0.00 m³/s
    Simulation completed!

Using the Web Interface
-----------------------

The framework includes a web-based interface for easier model setup and visualization.

1. Start the Web Server
~~~~~~~~~~~~~~~~~~~~~~~

::

    python gui/web/app.py

2. Open Your Browser
~~~~~~~~~~~~~~~~~~~~

Navigate to ``http://localhost:5000`` to access the web interface.

3. Create a New Project
~~~~~~~~~~~~~~~~~~~~~~~

* Click "New Project"
* Enter project details
* Configure your simulation parameters
* Add components and connections
* Run the simulation and view results

Working with Different Model Types
-----------------------------------

1D Hydraulic Models
~~~~~~~~~~~~~~~~~~~

For river channel modeling::

    {
        "type": "HydraulicModel",
        "name": "river_reach",
        "parameters": {
            "reach_file": "data/river_geometry.csv",
            "downstream_level": 10.0,
            "initial_flow": 50.0
        }
    }

2D Hydraulic Models
~~~~~~~~~~~~~~~~~~~

For floodplain modeling::

    {
        "type": "Model2D",
        "name": "floodplain",
        "parameters": {
            "mesh_file": "data/mesh.json",
            "initial_depth": 0.1
        }
    }

Deep Learning Models
~~~~~~~~~~~~~~~~~~~~

For AI-based forecasting::

    {
        "type": "LSTMModel",
        "name": "forecast_model",
        "parameters": {
            "model_path": "models/lstm_model.pth",
            "sequence_length": 24,
            "input_features": ["rainfall", "temperature"]
        }
    }

Data Input and Output
---------------------

Loading Data
~~~~~~~~~~~~

The framework supports various data formats::

    import pandas as pd
    from common.db_loader import load_from_db
    
    # From CSV
    rainfall_data = pd.read_csv("data/rainfall.csv", index_col=0, parse_dates=True)
    
    # From database (if available)
    spatial_data = load_from_db(
        "postgresql://user:pass@localhost/hydro_db",
        "SELECT * FROM catchments"
    )

Exporting Results
~~~~~~~~~~~~~~~~~

Save simulation results::

    # Get results from controller
    results = controller.get_results()
    
    # Save to CSV
    results_df = pd.DataFrame(results)
    results_df.to_csv("output/simulation_results.csv")
    
    # Save to JSON
    import json
    with open("output/results.json", "w") as f:
        json.dump(results, f, indent=2)

Visualization
-------------

Basic Plotting
~~~~~~~~~~~~~~

::

    import matplotlib.pyplot as plt
    
    # Plot time series
    plt.figure(figsize=(10, 6))
    plt.plot(results_df.index, results_df['outflow'])
    plt.xlabel('Time')
    plt.ylabel('Outflow (m³/s)')
    plt.title('Simulation Results')
    plt.grid(True)
    plt.show()

Interactive Plots
~~~~~~~~~~~~~~~~~

::

    import plotly.graph_objects as go
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=results_df.index,
        y=results_df['outflow'],
        mode='lines',
        name='Outflow'
    ))
    fig.update_layout(
        title='Interactive Simulation Results',
        xaxis_title='Time',
        yaxis_title='Outflow (m³/s)'
    )
    fig.show()

Next Steps
----------

Now that you've completed your first simulation:

1. Explore the :doc:`api/modules` documentation for detailed API reference
2. Check out the :doc:`examples` for more complex scenarios
3. Learn about :doc:`contributing` to the framework
4. Join our community discussions on GitHub

Common Patterns
---------------

Error Handling
~~~~~~~~~~~~~~

::

    from common.error_handler import ErrorHandler
    
    try:
        controller.step(inputs, dt=3600)
    except Exception as e:
        error_handler = ErrorHandler()
        error_handler.handle_error(e, context="simulation_step")

Performance Monitoring
~~~~~~~~~~~~~~~~~~~~~~

::

    from common.performance_monitor import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    # Run simulation
    controller.run_simulation()
    
    # Get performance metrics
    metrics = monitor.get_metrics()
    print(f"Execution time: {metrics['execution_time']:.2f} seconds")
    print(f"Memory usage: {metrics['peak_memory']:.2f} MB")

Troubleshooting
---------------

**Configuration errors**: Check JSON syntax and required parameters

**Import errors**: Ensure all dependencies are installed

**Memory issues**: Reduce time step or model resolution for large simulations

**Performance issues**: Enable performance monitoring to identify bottlenecks

For more help, see the full :doc:`api/modules` documentation or check our GitHub issues.