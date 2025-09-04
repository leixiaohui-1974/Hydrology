preissmann_model package
=========================

.. automodule:: preissmann_model
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

preissmann_model.model module
-----------------------------

.. automodule:: preissmann_model.model
   :members:
   :undoc-members:
   :show-inheritance:

preissmann_model.solver module
------------------------------

.. automodule:: preissmann_model.solver
   :members:
   :undoc-members:
   :show-inheritance:

preissmann_model.geometry module
--------------------------------

.. automodule:: preissmann_model.geometry
   :members:
   :undoc-members:
   :show-inheritance:

preissmann_model.boundary_conditions module
--------------------------------------------

.. automodule:: preissmann_model.boundary_conditions
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The preissmann_model package provides 1D hydraulic modeling capabilities using the Preissmann scheme
for solving the Saint-Venant equations. This package is designed for:

* **River and Channel Flow**: Unsteady flow in open channels
* **Urban Drainage**: Storm water and sewer systems
* **Flood Routing**: Flood wave propagation
* **Dam Break Analysis**: Rapid flow changes
* **Tidal Modeling**: Tidal flow in estuaries

Key Features
------------

* **Implicit Finite Difference**: Stable numerical scheme
* **Variable Cross-sections**: Support for complex geometries
* **Flexible Boundary Conditions**: Multiple BC types
* **Subcritical and Supercritical Flow**: Handles all flow regimes
* **Lateral Inflows**: Distributed and point sources
* **Structure Modeling**: Bridges, culverts, weirs

Key Classes and Functions
-------------------------

HydraulicModel Class
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: preissmann_model.model.HydraulicModel
   :members:
   :special-members: __init__

PreissmannSolver Class
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: preissmann_model.solver.PreissmannSolver
   :members:
   :special-members: __init__

ChannelGeometry Class
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: preissmann_model.geometry.ChannelGeometry
   :members:
   :special-members: __init__

CrossSection Class
~~~~~~~~~~~~~~~~~~

.. autoclass:: preissmann_model.geometry.CrossSection
   :members:
   :special-members: __init__

BoundaryCondition Classes
~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: preissmann_model.boundary_conditions.UpstreamFlowBC
   :members:
   :special-members: __init__

.. autoclass:: preissmann_model.boundary_conditions.DownstreamLevelBC
   :members:
   :special-members: __init__

.. autoclass:: preissmann_model.boundary_conditions.RatingCurveBC
   :members:
   :special-members: __init__

Usage Examples
--------------

Basic River Modeling
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.model import HydraulicModel
   from preissmann_model.geometry import ChannelGeometry, CrossSection
   from preissmann_model.boundary_conditions import UpstreamFlowBC, DownstreamLevelBC
   import numpy as np
   
   # Define channel geometry
   stations = np.linspace(0, 1000, 21)  # 1 km reach, 21 cross-sections
   cross_sections = []
   
   for x in stations:
       # Trapezoidal channel
       cs = CrossSection(
           station=x,
           bottom_elevation=100 - 0.001 * x,  # 0.1% slope
           bottom_width=10.0,
           side_slopes=[2.0, 2.0],  # 2H:1V side slopes
           manning_n=0.035
       )
       cross_sections.append(cs)
   
   geometry = ChannelGeometry(cross_sections)
   
   # Create hydraulic model
   model = HydraulicModel(
       name="river_reach",
       geometry=geometry,
       dt=60.0,  # 1-minute time step
       dx=50.0   # 50m spatial step
   )
   
   # Set boundary conditions
   upstream_bc = UpstreamFlowBC(
       flow_series=lambda t: 50.0 + 30.0 * np.sin(t / 3600.0)  # Sinusoidal flow
   )
   downstream_bc = DownstreamLevelBC(level=95.0)  # Fixed downstream level
   
   model.set_upstream_bc(upstream_bc)
   model.set_downstream_bc(downstream_bc)
   
   # Initialize model
   model.initialize()
   
   # Run simulation
   simulation_time = 3600 * 6  # 6 hours
   results = []
   
   for t in range(0, simulation_time, 60):
       model.step(dt=60.0)
       
       # Store results
       water_levels = model.get_water_levels()
       flows = model.get_flows()
       velocities = model.get_velocities()
       
       results.append({
           'time': t,
           'water_levels': water_levels.copy(),
           'flows': flows.copy(),
           'velocities': velocities.copy()
       })
       
       if t % 1800 == 0:  # Print every 30 minutes
           max_level = np.max(water_levels)
           max_flow = np.max(flows)
           print(f"Time: {t/3600:.1f}h, Max Level: {max_level:.2f}m, Max Flow: {max_flow:.1f}m³/s")

Flood Wave Routing
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.model import HydraulicModel
   import pandas as pd
   
   # Load flood hydrograph
   flood_data = pd.read_csv('flood_hydrograph.csv', parse_dates=['time'])
   
   def flood_hydrograph(t):
       """Interpolate flood hydrograph."""
       time_hours = t / 3600.0
       return np.interp(time_hours, flood_data['hours'], flood_data['flow'])
   
   # Create model with flood boundary condition
   model = HydraulicModel(
       name="flood_routing",
       geometry=geometry,
       dt=30.0  # Smaller time step for flood routing
   )
   
   # Flood boundary condition
   flood_bc = UpstreamFlowBC(flow_series=flood_hydrograph)
   model.set_upstream_bc(flood_bc)
   
   # Normal depth downstream
   from preissmann_model.boundary_conditions import NormalDepthBC
   normal_bc = NormalDepthBC(slope=0.001)
   model.set_downstream_bc(normal_bc)
   
   # Run flood simulation
   flood_duration = 3600 * 24  # 24 hours
   
   for t in range(0, flood_duration, 30):
       model.step(dt=30.0)
       
       # Check for overbank flow
       water_levels = model.get_water_levels()
       bank_elevations = model.get_bank_elevations()
       
       overbank_locations = np.where(water_levels > bank_elevations)[0]
       if len(overbank_locations) > 0:
           print(f"FLOOD WARNING at t={t/3600:.1f}h: Overbank flow at stations {overbank_locations}")

Urban Drainage Modeling
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.model import HydraulicModel
   from preissmann_model.geometry import CircularPipe, RectangularChannel
   
   # Create storm sewer system
   def create_sewer_system():
       pipes = []
       
       # Main trunk sewer (circular pipe)
       for i in range(10):
           pipe = CircularPipe(
               station=i * 100,
               diameter=1.5,  # 1.5m diameter
               invert_elevation=50 - 0.005 * i * 100,  # 0.5% slope
               manning_n=0.013
           )
           pipes.append(pipe)
       
       return ChannelGeometry(pipes)
   
   sewer_geometry = create_sewer_system()
   
   # Create sewer model
   sewer_model = HydraulicModel(
       name="storm_sewer",
       geometry=sewer_geometry,
       dt=10.0  # 10-second time step for urban drainage
   )
   
   # Rainfall-runoff input
   def storm_inflow(t):
       """Design storm hydrograph."""
       t_min = t / 60.0
       if t_min < 30:
           return 0.5 * t_min  # Rising limb
       elif t_min < 60:
           return 15.0 - 0.5 * (t_min - 30)  # Falling limb
       else:
           return 0.0
   
   # Set boundary conditions
   storm_bc = UpstreamFlowBC(flow_series=storm_inflow)
   outlet_bc = DownstreamLevelBC(level=48.0)  # Outlet level
   
   sewer_model.set_upstream_bc(storm_bc)
   sewer_model.set_downstream_bc(outlet_bc)
   
   # Add lateral inflows (catch basins)
   lateral_inflows = {
       200: lambda t: 0.1 * storm_inflow(t),  # 10% of main inflow
       400: lambda t: 0.15 * storm_inflow(t), # 15% of main inflow
       600: lambda t: 0.08 * storm_inflow(t)  # 8% of main inflow
   }
   
   for station, inflow_func in lateral_inflows.items():
       sewer_model.add_lateral_inflow(station, inflow_func)
   
   # Run storm simulation
   storm_duration = 3600 * 2  # 2 hours
   
   for t in range(0, storm_duration, 10):
       sewer_model.step(dt=10.0)
       
       # Check for surcharging
       water_levels = sewer_model.get_water_levels()
       pipe_tops = sewer_model.get_pipe_tops()
       
       surcharged = water_levels > pipe_tops
       if np.any(surcharged):
           surcharged_stations = np.where(surcharged)[0]
           print(f"SURCHARGE WARNING at t={t/60:.1f}min: Stations {surcharged_stations}")

Dam Break Analysis
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.model import HydraulicModel
   from preissmann_model.boundary_conditions import DamBreakBC
   
   # Create downstream valley geometry
   def create_valley_geometry():
       stations = np.linspace(0, 5000, 101)  # 5 km downstream
       cross_sections = []
       
       for i, x in enumerate(stations):
           # Valley widens downstream
           bottom_width = 20 + 0.01 * x
           bottom_elevation = 200 - 0.002 * x  # 0.2% slope
           
           cs = CrossSection(
               station=x,
               bottom_elevation=bottom_elevation,
               bottom_width=bottom_width,
               side_slopes=[3.0, 3.0],  # Gentle valley sides
               manning_n=0.035
           )
           cross_sections.append(cs)
       
       return ChannelGeometry(cross_sections)
   
   valley_geometry = create_valley_geometry()
   
   # Create dam break model
   dam_break_model = HydraulicModel(
       name="dam_break",
       geometry=valley_geometry,
       dt=5.0  # Small time step for dam break
   )
   
   # Dam break boundary condition
   dam_break_bc = DamBreakBC(
       reservoir_level=250.0,  # Initial reservoir level
       breach_width=50.0,      # Breach width
       breach_time=1800.0      # 30-minute breach formation
   )
   
   # Downstream boundary (far field)
   far_field_bc = DownstreamLevelBC(level=190.0)
   
   dam_break_model.set_upstream_bc(dam_break_bc)
   dam_break_model.set_downstream_bc(far_field_bc)
   
   # Run dam break simulation
   simulation_time = 3600 * 8  # 8 hours
   
   max_levels = []
   arrival_times = []
   
   for t in range(0, simulation_time, 5):
       dam_break_model.step(dt=5.0)
       
       water_levels = dam_break_model.get_water_levels()
       flows = dam_break_model.get_flows()
       
       # Track flood wave arrival
       if t == 0:
           initial_levels = water_levels.copy()
       
       # Detect flood wave arrival (1m rise above initial)
       wave_front = water_levels > (initial_levels + 1.0)
       
       if t % 300 == 0:  # Every 5 minutes
           max_flow = np.max(flows)
           max_level = np.max(water_levels)
           print(f"Time: {t/60:.0f}min, Max Flow: {max_flow:.0f}m³/s, Max Level: {max_level:.1f}m")

Tidal Modeling
~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.model import HydraulicModel
   from preissmann_model.boundary_conditions import TidalBC
   import numpy as np
   
   # Create estuary geometry
   def create_estuary_geometry():
       stations = np.linspace(0, 10000, 201)  # 10 km estuary
       cross_sections = []
       
       for x in stations:
           # Estuary widens toward ocean
           width = 100 + 0.02 * x  # Widens from 100m to 300m
           depth = 5 + 0.001 * x   # Deepens toward ocean
           
           cs = CrossSection(
               station=x,
               bottom_elevation=-depth,
               bottom_width=width,
               side_slopes=[0.5, 0.5],  # Steep banks
               manning_n=0.025
           )
           cross_sections.append(cs)
       
       return ChannelGeometry(cross_sections)
   
   estuary_geometry = create_estuary_geometry()
   
   # Create tidal model
   tidal_model = HydraulicModel(
       name="estuary_tides",
       geometry=estuary_geometry,
       dt=60.0  # 1-minute time step
   )
   
   # River inflow (upstream)
   river_flow = 100.0  # Constant 100 m³/s
   river_bc = UpstreamFlowBC(flow_series=lambda t: river_flow)
   
   # Tidal boundary (downstream)
   def tidal_elevation(t):
       """M2 tidal constituent (12.42 hour period)."""
       omega = 2 * np.pi / (12.42 * 3600)  # M2 frequency
       return 2.0 * np.sin(omega * t)  # 2m tidal range
   
   tidal_bc = TidalBC(elevation_series=tidal_elevation)
   
   tidal_model.set_upstream_bc(river_bc)
   tidal_model.set_downstream_bc(tidal_bc)
   
   # Run tidal simulation (2 tidal cycles)
   tidal_period = 12.42 * 3600
   simulation_time = int(2 * tidal_period)
   
   tidal_results = []
   
   for t in range(0, simulation_time, 60):
       tidal_model.step(dt=60.0)
       
       water_levels = tidal_model.get_water_levels()
       flows = tidal_model.get_flows()
       
       # Store results at key locations
       tidal_results.append({
           'time': t / 3600.0,  # Hours
           'ocean_level': water_levels[-1],
           'mid_estuary_level': water_levels[len(water_levels)//2],
           'river_level': water_levels[0],
           'ocean_flow': flows[-1],
           'river_flow': flows[0]
       })
   
   # Analyze tidal propagation
   import pandas as pd
   tidal_df = pd.DataFrame(tidal_results)
   
   print("Tidal Analysis:")
   print(f"Ocean tidal range: {tidal_df['ocean_level'].max() - tidal_df['ocean_level'].min():.2f}m")
   print(f"Mid-estuary range: {tidal_df['mid_estuary_level'].max() - tidal_df['mid_estuary_level'].min():.2f}m")
   print(f"River tidal range: {tidal_df['river_level'].max() - tidal_df['river_level'].min():.2f}m")

Advanced Features
-----------------

Structure Modeling
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.structures import Bridge, Culvert, Weir
   
   # Add bridge to model
   bridge = Bridge(
       station=500.0,
       deck_elevation=105.0,
       pier_width=2.0,
       num_piers=2,
       contraction_coefficient=0.95
   )
   
   model.add_structure(bridge)
   
   # Add culvert
   culvert = Culvert(
       station=1200.0,
       diameter=3.0,
       length=50.0,
       inlet_loss=0.5,
       outlet_loss=1.0,
       friction_loss=0.02
   )
   
   model.add_structure(culvert)
   
   # Add weir
   weir = Weir(
       station=800.0,
       crest_elevation=102.0,
       length=20.0,
       discharge_coefficient=1.7
   )
   
   model.add_structure(weir)

Adaptive Time Stepping
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.solver import AdaptiveTimeStep
   
   # Enable adaptive time stepping
   adaptive_solver = AdaptiveTimeStep(
       min_dt=1.0,      # Minimum time step (seconds)
       max_dt=300.0,    # Maximum time step (seconds)
       target_cfl=0.8,  # Target CFL number
       max_iterations=10 # Maximum iterations per time step
   )
   
   model.set_solver(adaptive_solver)
   
   # Run with adaptive time stepping
   while model.current_time < simulation_time:
       dt_used = model.step_adaptive()
       print(f"Time: {model.current_time:.1f}s, dt used: {dt_used:.1f}s")

Parallel Processing
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.parallel import ParallelSolver
   import multiprocessing as mp
   
   # Create parallel solver
   num_cores = mp.cpu_count()
   parallel_solver = ParallelSolver(
       num_processes=num_cores - 1,
       domain_decomposition='automatic'
   )
   
   # Large river system
   large_model = HydraulicModel(
       name="large_river_system",
       geometry=large_geometry,
       solver=parallel_solver
   )
   
   # Run in parallel
   large_model.run_parallel(simulation_time)

Model Calibration
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preissmann_model.calibration import AutoCalibration
   from scipy.optimize import minimize
   
   # Load observed data
   observed_data = pd.read_csv('observed_levels.csv')
   
   def objective_function(parameters):
       """Objective function for calibration."""
       # Update model parameters
       model.update_manning_n(parameters[0])
       model.update_roughness(parameters[1])
       
       # Run model
       model.reset()
       simulated_levels = []
       
       for t in range(0, simulation_time, 60):
           model.step(dt=60.0)
           levels = model.get_water_levels()
           simulated_levels.append(levels[observation_station])
       
       # Calculate RMSE
       simulated = np.array(simulated_levels)
       observed = observed_data['level'].values
       rmse = np.sqrt(np.mean((simulated - observed) ** 2))
       
       return rmse
   
   # Calibrate model
   initial_params = [0.035, 0.025]  # Initial Manning's n values
   bounds = [(0.020, 0.050), (0.015, 0.040)]  # Parameter bounds
   
   result = minimize(
       objective_function,
       initial_params,
       method='L-BFGS-B',
       bounds=bounds
   )
   
   print(f"Calibrated parameters: {result.x}")
   print(f"Final RMSE: {result.fun:.3f}m")

Configuration and Parameters
----------------------------

Numerical Parameters
~~~~~~~~~~~~~~~~~~~~

**Time Step Selection:**

- **Stability**: Courant number < 1.0
- **Accuracy**: Smaller time steps for rapid changes
- **Efficiency**: Balance accuracy vs. computation time

**Spatial Discretization:**

- **Grid spacing**: Typically 10-100m for rivers
- **Cross-section spacing**: Based on geometry changes
- **Convergence**: Refine grid until results stabilize

**Solver Settings:**

- **Convergence tolerance**: 1e-6 for water levels
- **Maximum iterations**: 10-20 per time step
- **Relaxation factor**: 0.5-1.0 for stability

Physical Parameters
~~~~~~~~~~~~~~~~~~~

**Manning's Roughness:**

- Natural channels: 0.025-0.075
- Concrete channels: 0.012-0.020
- Vegetated channels: 0.035-0.100

**Boundary Conditions:**

- Upstream: Flow hydrograph or stage
- Downstream: Stage, rating curve, or normal depth
- Lateral: Distributed or point inflows

Performance Optimization
------------------------

Computational Efficiency
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Optimize for speed
   model.set_solver_options({
       'matrix_solver': 'sparse_lu',  # Use sparse matrix solver
       'preconditioner': 'ilu',       # Incomplete LU preconditioner
       'convergence_tolerance': 1e-4, # Relaxed tolerance
       'max_iterations': 15           # Limit iterations
   })
   
   # Use vectorized operations
   model.enable_vectorization(True)
   
   # Optimize memory usage
   model.set_memory_options({
       'store_history': False,        # Don't store all time steps
       'output_frequency': 10,        # Output every 10 time steps
       'compress_output': True        # Compress output data
   })

Error Handling and Debugging
----------------------------

Common Issues
~~~~~~~~~~~~~

**Numerical Instability:**

- Reduce time step
- Check boundary conditions
- Verify geometry data
- Use implicit solver

**Convergence Problems:**

- Increase maximum iterations
- Adjust relaxation factor
- Check for dry cells
- Verify initial conditions

**Mass Conservation:**

- Check boundary condition consistency
- Verify lateral inflow data
- Monitor mass balance errors
- Use conservative discretization

Debugging Tools
~~~~~~~~~~~~~~~

.. code-block:: python

   # Enable detailed logging
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   # Monitor solver convergence
   model.enable_convergence_monitoring(True)
   
   # Check mass balance
   mass_balance = model.check_mass_balance()
   print(f"Mass balance error: {mass_balance:.6f}")
   
   # Visualize results
   model.plot_water_surface()
   model.plot_velocity_profile()
   model.plot_convergence_history()

Validation and Verification
---------------------------

Analytical Solutions
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Test against analytical solution
   from preissmann_model.validation import AnalyticalTests
   
   # Kinematic wave test
   kinematic_test = AnalyticalTests.kinematic_wave(
       length=1000.0,
       slope=0.001,
       manning_n=0.035,
       inflow_rate=10.0
   )
   
   # Compare with model results
   analytical_levels = kinematic_test.get_water_levels()
   model_levels = model.get_water_levels()
   
   rmse = np.sqrt(np.mean((analytical_levels - model_levels) ** 2))
   print(f"RMSE vs analytical solution: {rmse:.4f}m")

Benchmark Problems
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Standard benchmark tests
   from preissmann_model.benchmarks import Benchmarks
   
   # Dam break benchmark
   dam_break_benchmark = Benchmarks.dam_break_wet_bed()
   model_result = model.run_benchmark(dam_break_benchmark)
   
   # Compare with reference solution
   benchmark_score = dam_break_benchmark.evaluate(model_result)
   print(f"Benchmark score: {benchmark_score:.3f}")