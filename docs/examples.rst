Examples
=========

This section provides practical examples of using the Hydrology Framework for various scenarios.

.. toctree::
   :maxdepth: 2

   examples/basic_runoff
   examples/river_routing
   examples/flood_modeling
   examples/ml_forecasting
   examples/real_time_processing

Basic Examples
--------------

Simple Runoff Calculation
~~~~~~~~~~~~~~~~~~~~~~~~~~

This example demonstrates basic runoff calculation using the SCS Curve Number method::

    from hydro_model.runoff import SCSCurveNumberModule
    import numpy as np
    
    # Create runoff module
    runoff_module = SCSCurveNumberModule(
        curve_number=75,
        area_km2=10.0,
        initial_abstraction_ratio=0.2
    )
    
    # Rainfall data (mm)
    rainfall = np.array([0, 5, 15, 25, 10, 2, 0])
    
    # Calculate runoff for each time step
    runoff_results = []
    for rain in rainfall:
        runoff = runoff_module.run(rain, dt=3600)  # 1-hour time step
        runoff_results.append(runoff)
        print(f"Rainfall: {rain:4.1f} mm, Runoff: {runoff:6.3f} m³/s")

River Channel Routing
~~~~~~~~~~~~~~~~~~~~~

Example of routing flow through a river channel::

    from hydro_model.routing import SimpleRouting
    import pandas as pd
    
    # Create routing module
    routing = SimpleRouting(
        k_q=0.5,  # Quick flow recession constant
        k_s=0.1   # Slow flow recession constant
    )
    
    # Input hydrograph
    inflow = [10, 25, 45, 60, 40, 25, 15, 10, 8, 6]
    
    # Route the hydrograph
    outflow = []
    for q_in in inflow:
        q_out = routing.run(q_in, dt=3600)
        outflow.append(q_out)
    
    # Create results DataFrame
    results = pd.DataFrame({
        'inflow': inflow,
        'outflow': outflow
    })
    print(results)

Advanced Examples
-----------------

Coupled 1D-2D Modeling
~~~~~~~~~~~~~~~~~~~~~~~

Combining 1D river modeling with 2D floodplain modeling::

    from preissmann_model.model import HydraulicModel
    from model_2d.model import Model2D
    from common.controller import SimulationController
    from common.junction import Junction
    
    # Load river geometry and 2D mesh
    river_reach = load_river_geometry("data/river.csv")
    floodplain_mesh = load_2d_mesh("data/floodplain.json")
    
    # Create models
    river_model = HydraulicModel(
        name="main_river",
        reach=river_reach,
        dt=60,  # 1-minute time step
        downstream_level=10.0
    )
    
    floodplain_model = Model2D(
        name="floodplain",
        mesh=floodplain_mesh
    )
    
    # Create junction for coupling
    junction = Junction(
        name="river_floodplain_junction",
        junction_type="overflow_weir",
        parameters={"weir_coefficient": 1.5, "weir_length": 100.0}
    )
    
    # Set up controller
    controller = SimulationController()
    controller.add_component(river_model)
    controller.add_component(floodplain_model)
    controller.add_component(junction)
    
    # Define connections
    controller.add_connection("main_river", "river_floodplain_junction")
    controller.add_connection("river_floodplain_junction", "floodplain")
    
    # Run simulation
    for t in range(0, 3600, 60):  # 1 hour simulation
        # Set boundary conditions
        upstream_flow = get_upstream_flow(t)
        inputs = {"main_river": {"upstream_flow": upstream_flow}}
        
        # Step simulation
        controller.step(inputs, dt=60)
        
        # Log results
        river_levels = river_model.get_water_levels()
        floodplain_depths = floodplain_model.get_water_depths()
        
        print(f"Time: {t:4d}s, Max river level: {max(river_levels):.2f}m, "
              f"Max floodplain depth: {max(floodplain_depths):.2f}m")

Machine Learning Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using LSTM for flow forecasting::

    from dl_model.lstm_model import LSTMModel
    import pandas as pd
    import numpy as np
    
    # Load historical data
    data = pd.read_csv("data/historical_flows.csv", parse_dates=['date'], index_col='date')
    
    # Create LSTM model
    lstm_model = LSTMModel(
        name="flow_forecast",
        model_path="models/trained_lstm.pth",
        seq_len=24,  # 24-hour sequence
        input_features=["rainfall", "temperature", "humidity"],
        inflow_names=["upstream_flow"]
    )
    
    # Prepare input sequence
    recent_data = data.tail(24)
    
    # Set global inputs (weather data)
    global_inputs = {
        "rainfall": recent_data['rainfall'].values,
        "temperature": recent_data['temperature'].values,
        "humidity": recent_data['humidity'].values
    }
    lstm_model.set_global_inputs(global_inputs)
    
    # Make forecast
    inflows = {"upstream_flow": recent_data['upstream_flow'].iloc[-1]}
    lstm_model.step(inflows, dt=3600)
    
    forecast = lstm_model.get_outflow()
    print(f"Forecasted flow: {forecast:.2f} m³/s")

Real-time Data Processing
~~~~~~~~~~~~~~~~~~~~~~~~~

Processing live data streams::

    from common.controller import SimulationController
    from common.performance_monitor import PerformanceMonitor
    import time
    import threading
    
    class RealTimeProcessor:
        def __init__(self, controller):
            self.controller = controller
            self.monitor = PerformanceMonitor()
            self.running = False
            
        def start_processing(self):
            self.running = True
            self.monitor.start_monitoring()
            
            # Start processing thread
            processing_thread = threading.Thread(target=self._process_loop)
            processing_thread.start()
            
        def _process_loop(self):
            while self.running:
                try:
                    # Get real-time data
                    current_data = self._fetch_real_time_data()
                    
                    # Process data
                    self.controller.step(current_data, dt=300)  # 5-minute steps
                    
                    # Get results
                    results = self.controller.get_results()
                    
                    # Check for alerts
                    self._check_alerts(results)
                    
                    # Wait for next cycle
                    time.sleep(300)  # 5 minutes
                    
                except Exception as e:
                    print(f"Processing error: {e}")
                    time.sleep(60)  # Wait 1 minute before retry
                    
        def _fetch_real_time_data(self):
            # Simulate fetching real-time data
            return {
                "rainfall_station_1": {"rainfall": np.random.exponential(2.0)},
                "flow_gauge_1": {"flow": np.random.normal(50, 10)}
            }
            
        def _check_alerts(self, results):
            # Check for flood warnings
            for component_name, result in results.items():
                if 'water_level' in result and result['water_level'] > 15.0:
                    print(f"FLOOD WARNING: {component_name} water level: {result['water_level']:.2f}m")
                    
        def stop_processing(self):
            self.running = False
            metrics = self.monitor.get_metrics()
            print(f"Processing stopped. Performance metrics: {metrics}")
    
    # Usage
    controller = SimulationController()
    # ... add components ...
    
    processor = RealTimeProcessor(controller)
    processor.start_processing()
    
    # Run for some time, then stop
    time.sleep(3600)  # Run for 1 hour
    processor.stop_processing()

Performance Optimization
~~~~~~~~~~~~~~~~~~~~~~~~

Optimizing simulations for large-scale models::

    from common.parallel_controller import ParallelController
    from common.performance_monitor import PerformanceMonitor
    import multiprocessing as mp
    
    # Create parallel controller
    num_cores = mp.cpu_count()
    parallel_controller = ParallelController(num_processes=num_cores-1)
    
    # Add components to parallel controller
    for i in range(10):  # 10 catchments
        catchment = create_catchment_model(f"catchment_{i}")
        parallel_controller.add_component(catchment)
    
    # Set up performance monitoring
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    # Run parallel simulation
    simulation_time = 86400  # 24 hours
    dt = 3600  # 1 hour time step
    
    for t in range(0, simulation_time, dt):
        # Prepare inputs for all components
        inputs = {}
        for i in range(10):
            rainfall = get_rainfall_data(f"catchment_{i}", t)
            inputs[f"catchment_{i}"] = {"rainfall": rainfall}
        
        # Step all components in parallel
        parallel_controller.step_parallel(inputs, dt)
        
        if t % (6 * 3600) == 0:  # Every 6 hours
            metrics = monitor.get_current_metrics()
            print(f"Time: {t/3600:2.0f}h, CPU: {metrics['cpu_percent']:.1f}%, "
                  f"Memory: {metrics['memory_mb']:.1f}MB")
    
    # Get final performance metrics
    final_metrics = monitor.get_metrics()
    print(f"Simulation completed in {final_metrics['execution_time']:.2f} seconds")
    print(f"Peak memory usage: {final_metrics['peak_memory']:.2f} MB")
    
    # Cleanup
    parallel_controller.cleanup()

Data Analysis and Visualization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Analyzing simulation results::

    import pandas as pd
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    # Load simulation results
    results = pd.read_csv("output/simulation_results.csv", 
                         parse_dates=['timestamp'], index_col='timestamp')
    
    # Basic statistics
    print("Simulation Results Summary:")
    print(results.describe())
    
    # Time series analysis
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    # Plot rainfall
    axes[0].bar(results.index, results['rainfall'], alpha=0.7, color='blue')
    axes[0].set_ylabel('Rainfall (mm/h)')
    axes[0].set_title('Rainfall Input')
    axes[0].grid(True)
    
    # Plot flow
    axes[1].plot(results.index, results['flow'], color='red', linewidth=2)
    axes[1].set_ylabel('Flow (m³/s)')
    axes[1].set_title('Simulated Flow')
    axes[1].grid(True)
    
    # Plot water level
    axes[2].plot(results.index, results['water_level'], color='green', linewidth=2)
    axes[2].set_ylabel('Water Level (m)')
    axes[2].set_title('Water Level')
    axes[2].set_xlabel('Time')
    axes[2].grid(True)
    
    plt.tight_layout()
    plt.savefig('output/simulation_plots.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # Interactive plot with Plotly
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=('Rainfall', 'Flow', 'Water Level'),
        vertical_spacing=0.08
    )
    
    # Add traces
    fig.add_trace(
        go.Bar(x=results.index, y=results['rainfall'], name='Rainfall'),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(x=results.index, y=results['flow'], 
                  mode='lines', name='Flow', line=dict(color='red')),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(x=results.index, y=results['water_level'], 
                  mode='lines', name='Water Level', line=dict(color='green')),
        row=3, col=1
    )
    
    # Update layout
    fig.update_layout(
        height=800,
        title_text="Hydrology Simulation Results",
        showlegend=False
    )
    
    fig.update_yaxes(title_text="Rainfall (mm/h)", row=1, col=1)
    fig.update_yaxes(title_text="Flow (m³/s)", row=2, col=1)
    fig.update_yaxes(title_text="Water Level (m)", row=3, col=1)
    fig.update_xaxes(title_text="Time", row=3, col=1)
    
    # Save interactive plot
    fig.write_html("output/interactive_results.html")
    fig.show()
    
    # Statistical analysis
    from scipy import stats
    
    # Correlation analysis
    correlation_matrix = results[['rainfall', 'flow', 'water_level']].corr()
    print("\nCorrelation Matrix:")
    print(correlation_matrix)
    
    # Peak flow analysis
    peak_flows = results['flow'].nlargest(10)
    print("\nTop 10 Peak Flows:")
    for i, (timestamp, flow) in enumerate(peak_flows.items(), 1):
        print(f"{i:2d}. {timestamp}: {flow:.2f} m³/s")
    
    # Flow duration curve
    sorted_flows = results['flow'].sort_values(ascending=False)
    exceedance_prob = np.arange(1, len(sorted_flows) + 1) / len(sorted_flows) * 100
    
    plt.figure(figsize=(10, 6))
    plt.semilogy(exceedance_prob, sorted_flows)
    plt.xlabel('Exceedance Probability (%)')
    plt.ylabel('Flow (m³/s)')
    plt.title('Flow Duration Curve')
    plt.grid(True)
    plt.savefig('output/flow_duration_curve.png', dpi=300, bbox_inches='tight')
    plt.show()

Testing and Validation
~~~~~~~~~~~~~~~~~~~~~~

Validating model results against observations::

    import numpy as np
    from sklearn.metrics import mean_squared_error, r2_score
    import matplotlib.pyplot as plt
    
    # Load observed and simulated data
    observed = pd.read_csv("data/observed_flows.csv", 
                          parse_dates=['date'], index_col='date')
    simulated = pd.read_csv("output/simulated_flows.csv", 
                           parse_dates=['date'], index_col='date')
    
    # Align datasets
    common_dates = observed.index.intersection(simulated.index)
    obs_aligned = observed.loc[common_dates, 'flow']
    sim_aligned = simulated.loc[common_dates, 'flow']
    
    # Calculate performance metrics
    rmse = np.sqrt(mean_squared_error(obs_aligned, sim_aligned))
    r2 = r2_score(obs_aligned, sim_aligned)
    nash_sutcliffe = 1 - (np.sum((obs_aligned - sim_aligned) ** 2) / 
                         np.sum((obs_aligned - np.mean(obs_aligned)) ** 2))
    
    print(f"Model Performance Metrics:")
    print(f"RMSE: {rmse:.3f} m³/s")
    print(f"R²: {r2:.3f}")
    print(f"Nash-Sutcliffe Efficiency: {nash_sutcliffe:.3f}")
    
    # Scatter plot
    plt.figure(figsize=(10, 8))
    plt.scatter(obs_aligned, sim_aligned, alpha=0.6, s=20)
    
    # 1:1 line
    min_val = min(obs_aligned.min(), sim_aligned.min())
    max_val = max(obs_aligned.max(), sim_aligned.max())
    plt.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2, label='1:1 Line')
    
    plt.xlabel('Observed Flow (m³/s)')
    plt.ylabel('Simulated Flow (m³/s)')
    plt.title(f'Observed vs Simulated Flow\nR² = {r2:.3f}, NSE = {nash_sutcliffe:.3f}')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.axis('equal')
    plt.savefig('output/validation_scatter.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # Time series comparison
    plt.figure(figsize=(15, 6))
    plt.plot(obs_aligned.index, obs_aligned.values, 'b-', linewidth=2, label='Observed', alpha=0.8)
    plt.plot(sim_aligned.index, sim_aligned.values, 'r-', linewidth=1.5, label='Simulated', alpha=0.8)
    plt.xlabel('Date')
    plt.ylabel('Flow (m³/s)')
    plt.title('Observed vs Simulated Flow Time Series')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig('output/validation_timeseries.png', dpi=300, bbox_inches='tight')
    plt.show()

For more detailed examples and tutorials, visit our `GitHub repository <https://github.com/your-org/hydrology-framework>`_.