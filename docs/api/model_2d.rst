model_2d package
================

.. automodule:: model_2d
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

model_2d.model module
---------------------

.. automodule:: model_2d.model
   :members:
   :undoc-members:
   :show-inheritance:

model_2d.solver module
----------------------

.. automodule:: model_2d.solver
   :members:
   :undoc-members:
   :show-inheritance:

model_2d.mesh module
--------------------

.. automodule:: model_2d.mesh
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The model_2d package provides 2D hydraulic modeling capabilities for the Hydrology Framework.
It implements finite volume methods for solving the 2D shallow water equations, suitable for:

* **Floodplain Modeling**: Urban and rural flood inundation
* **Coastal Modeling**: Storm surge and tsunami propagation
* **Dam Break Analysis**: 2D flood wave propagation
* **Urban Drainage**: Surface water flow in cities
* **Wetland Modeling**: Flow in complex topography
* **River Overbank Flow**: Floodplain inundation modeling

Key Features
------------

* **Unstructured Meshes**: Triangular and quadrilateral elements
* **Wet-Dry Treatment**: Robust wetting and drying algorithms
* **Multiple Solvers**: Explicit and implicit time integration
* **Adaptive Time Stepping**: Automatic time step control
* **Parallel Processing**: Multi-core and GPU acceleration
* **Flexible Boundary Conditions**: Inflow, outflow, and wall boundaries

Key Classes and Functions
-------------------------

Model2D Class
~~~~~~~~~~~~~

.. autoclass:: model_2d.model.Model2D
   :members:
   :special-members: __init__

ShallowWaterSolver Class
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: model_2d.solver.ShallowWaterSolver
   :members:
   :special-members: __init__

FiniteVolumeSolver Class
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: model_2d.solver.FiniteVolumeSolver
   :members:
   :special-members: __init__

Mesh2D Class
~~~~~~~~~~~~

.. autoclass:: model_2d.mesh.Mesh2D
   :members:
   :special-members: __init__

TriangularMesh Class
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: model_2d.mesh.TriangularMesh
   :members:
   :special-members: __init__

QuadrilateralMesh Class
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: model_2d.mesh.QuadrilateralMesh
   :members:
   :special-members: __init__

Usage Examples
--------------

Basic 2D Flood Modeling
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.model import Model2D
   from model_2d.mesh import TriangularMesh
   from model_2d.solver import ShallowWaterSolver
   import numpy as np
   
   # Create triangular mesh
   mesh = TriangularMesh.from_file("floodplain_mesh.msh")
   
   # Alternative: create simple rectangular mesh
   # mesh = TriangularMesh.create_rectangle(
   #     x_min=0, x_max=1000, y_min=0, y_max=500,
   #     nx=50, ny=25
   # )
   
   # Create 2D model
   model = Model2D(
       name="floodplain_model",
       mesh=mesh,
       source_cell_id=0,      # Inflow cell
       outlet_edge_id=100     # Outlet edge
   )
   
   # Set initial conditions
   initial_depth = np.zeros(mesh.num_cells)
   initial_velocity_x = np.zeros(mesh.num_cells)
   initial_velocity_y = np.zeros(mesh.num_cells)
   
   model.set_initial_conditions(
       depth=initial_depth,
       velocity_x=initial_velocity_x,
       velocity_y=initial_velocity_y
   )
   
   # Set boundary conditions
   # Inflow boundary
   def inflow_hydrograph(t):
       """Flood hydrograph."""
       if t < 3600:  # 1 hour rising
           return 100 * t / 3600
       elif t < 7200:  # 1 hour peak
           return 100.0
       elif t < 14400:  # 2 hours falling
           return 100 * (14400 - t) / 7200
       else:
           return 0.0
   
   model.set_inflow_bc(inflow_hydrograph)
   
   # Outlet boundary (free outflow)
   model.set_outlet_bc("free_outflow")
   
   # Run simulation
   simulation_time = 3600 * 6  # 6 hours
   dt = 10.0  # 10-second time step
   
   results = []
   
   for t in range(0, simulation_time, int(dt)):
       # Step the model
       model.step({}, dt)
       
       # Get current state
       depths = model.get_water_depths()
       velocities_x, velocities_y = model.get_velocities()
       
       # Store results every 10 minutes
       if t % 600 == 0:
           results.append({
               'time': t,
               'max_depth': np.max(depths),
               'total_volume': np.sum(depths * mesh.cell_areas),
               'max_velocity': np.max(np.sqrt(velocities_x**2 + velocities_y**2))
           })
           
           print(f"Time: {t/3600:.1f}h, Max depth: {np.max(depths):.2f}m, "
                 f"Max velocity: {np.max(np.sqrt(velocities_x**2 + velocities_y**2)):.2f}m/s")
   
   # Save final results
   model.save_results("flood_results.vtk")

Dam Break Simulation
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.model import Model2D
   from model_2d.mesh import QuadrilateralMesh
   import numpy as np
   
   # Create structured mesh for dam break
   mesh = QuadrilateralMesh.create_rectangle(
       x_min=0, x_max=2000, y_min=0, y_max=1000,
       nx=100, ny=50
   )
   
   # Load topography
   elevations = load_topography("dam_break_topo.txt")
   mesh.set_bed_elevations(elevations)
   
   # Create dam break model
   dam_break_model = Model2D(
       name="dam_break",
       mesh=mesh
   )
   
   # Set initial conditions (reservoir upstream, dry downstream)
   initial_depth = np.zeros(mesh.num_cells)
   
   # Reservoir area (upstream of dam at x=500m)
   reservoir_cells = mesh.cell_centers[:, 0] < 500
   initial_depth[reservoir_cells] = 10.0  # 10m initial depth
   
   dam_break_model.set_initial_conditions(
       depth=initial_depth,
       velocity_x=np.zeros(mesh.num_cells),
       velocity_y=np.zeros(mesh.num_cells)
   )
   
   # No boundary conditions needed (closed domain)
   
   # Run dam break simulation
   simulation_time = 3600  # 1 hour
   dt = 0.5  # Small time step for dam break
   
   # Store results for animation
   time_series = []
   
   for t in np.arange(0, simulation_time, dt):
       dam_break_model.step({}, dt)
       
       # Store results every 30 seconds
       if t % 30 == 0:
           depths = dam_break_model.get_water_depths()
           velocities_x, velocities_y = dam_break_model.get_velocities()
           
           time_series.append({
               'time': t,
               'depths': depths.copy(),
               'velocities_x': velocities_x.copy(),
               'velocities_y': velocities_y.copy()
           })
           
           # Find flood front position
           wet_cells = depths > 0.01  # 1cm threshold
           if np.any(wet_cells):
               max_x = np.max(mesh.cell_centers[wet_cells, 0])
               print(f"Time: {t:6.1f}s, Flood front at x = {max_x:6.1f}m")
   
   # Create animation
   create_flood_animation(time_series, mesh, "dam_break_animation.mp4")

Urban Flood Modeling
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.model import Model2D
   from model_2d.mesh import TriangularMesh
   from model_2d.buildings import BuildingModule
   import geopandas as gpd
   
   # Load urban mesh with buildings
   mesh = TriangularMesh.from_shapefile("urban_area.shp")
   
   # Load building footprints
   buildings = gpd.read_file("buildings.shp")
   
   # Create urban flood model
   urban_model = Model2D(
       name="urban_flood",
       mesh=mesh
   )
   
   # Add building module
   building_module = BuildingModule(buildings)
   urban_model.add_module(building_module)
   
   # Set rainfall input
   def design_storm(t):
       """Chicago design storm."""
       t_min = t / 60.0
       if t_min < 60:
           # Intensity in mm/hr
           intensity = 25.4 * (10 / (t_min + 10))**0.8
           return intensity / 3600  # Convert to mm/s
       else:
           return 0.0
   
   # Apply rainfall to all cells
   for cell_id in range(mesh.num_cells):
       urban_model.add_source(cell_id, design_storm)
   
   # Set drainage system (simplified)
   storm_drains = [
       {'cell_id': 100, 'capacity': 0.5},  # 0.5 m³/s capacity
       {'cell_id': 200, 'capacity': 0.3},
       {'cell_id': 300, 'capacity': 0.4}
   ]
   
   for drain in storm_drains:
       urban_model.add_sink(drain['cell_id'], drain['capacity'])
   
   # Run urban flood simulation
   storm_duration = 3600 * 2  # 2 hours
   dt = 5.0  # 5-second time step
   
   flood_depths = []
   
   for t in range(0, storm_duration, int(dt)):
       urban_model.step({}, dt)
       
       depths = urban_model.get_water_depths()
       
       # Check for flooding (depth > 0.1m)
       flooded_area = np.sum(mesh.cell_areas[depths > 0.1])
       
       if t % 300 == 0:  # Every 5 minutes
           print(f"Time: {t/60:4.0f}min, Flooded area: {flooded_area/1000:.1f} ha")
       
       flood_depths.append({
           'time': t,
           'depths': depths.copy(),
           'flooded_area': flooded_area
       })
   
   # Analyze results
   max_depths = np.max([result['depths'] for result in flood_depths], axis=0)
   
   # Export flood hazard map
   urban_model.export_flood_map(max_depths, "urban_flood_hazard.tif")

Coastal Storm Surge Modeling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.model import Model2D
   from model_2d.mesh import TriangularMesh
   from model_2d.boundary_conditions import TidalBC, WindStressBC
   import numpy as np
   
   # Load coastal mesh
   coastal_mesh = TriangularMesh.from_file("coastal_domain.msh")
   
   # Create storm surge model
   surge_model = Model2D(
       name="storm_surge",
       mesh=coastal_mesh
   )
   
   # Set initial conditions (mean sea level)
   initial_depth = np.ones(coastal_mesh.num_cells) * 2.0  # 2m mean depth
   surge_model.set_initial_conditions(
       depth=initial_depth,
       velocity_x=np.zeros(coastal_mesh.num_cells),
       velocity_y=np.zeros(coastal_mesh.num_cells)
   )
   
   # Ocean boundary (tidal + storm surge)
   def storm_surge_elevation(t):
       """Storm surge + astronomical tide."""
       # Astronomical tide (M2 component)
       tide = 1.0 * np.sin(2 * np.pi * t / (12.42 * 3600))
       
       # Storm surge (simplified)
       storm_peak_time = 6 * 3600  # Peak at 6 hours
       if t < storm_peak_time:
           surge = 3.0 * (t / storm_peak_time)
       else:
           surge = 3.0 * np.exp(-(t - storm_peak_time) / (2 * 3600))
       
       return tide + surge
   
   # Set ocean boundary
   ocean_boundary_edges = coastal_mesh.get_boundary_edges("ocean")
   tidal_bc = TidalBC(storm_surge_elevation)
   surge_model.set_boundary_condition(ocean_boundary_edges, tidal_bc)
   
   # Wind stress boundary condition
   def wind_stress(t):
       """Hurricane wind stress."""
       # Wind speed (m/s)
       max_wind = 50.0  # 50 m/s hurricane
       wind_speed = max_wind * np.sin(np.pi * t / (12 * 3600))  # 12-hour storm
       
       # Wind stress (N/m²)
       rho_air = 1.225  # kg/m³
       cd = 0.002  # Drag coefficient
       stress = rho_air * cd * wind_speed**2
       
       return stress
   
   wind_bc = WindStressBC(wind_stress, direction=45)  # 45° wind direction
   surge_model.add_wind_stress(wind_bc)
   
   # Run storm surge simulation
   storm_duration = 3600 * 24  # 24 hours
   dt = 30.0  # 30-second time step
   
   surge_results = []
   
   for t in range(0, storm_duration, int(dt)):
       surge_model.step({}, dt)
       
       depths = surge_model.get_water_depths()
       velocities_x, velocities_y = surge_model.get_velocities()
       
       # Calculate surge height (depth - initial depth)
       surge_height = depths - initial_depth
       
       if t % 1800 == 0:  # Every 30 minutes
           max_surge = np.max(surge_height)
           max_velocity = np.max(np.sqrt(velocities_x**2 + velocities_y**2))
           print(f"Time: {t/3600:4.1f}h, Max surge: {max_surge:.2f}m, Max velocity: {max_velocity:.2f}m/s")
       
       surge_results.append({
           'time': t,
           'surge_height': surge_height.copy(),
           'velocities': np.sqrt(velocities_x**2 + velocities_y**2)
       })
   
   # Export maximum surge heights
   max_surge_heights = np.max([result['surge_height'] for result in surge_results], axis=0)
   surge_model.export_results(max_surge_heights, "max_surge_heights.vtk")

Coupled 1D-2D Modeling
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.model import Model2D
   from preissmann_model.model import HydraulicModel
   from common.controller import SimulationController
   from common.junction import Junction
   
   # Create 1D river model
   river_model = HydraulicModel(
       name="main_river",
       reach=river_geometry,
       dt=60.0
   )
   
   # Create 2D floodplain model
   floodplain_model = Model2D(
       name="floodplain",
       mesh=floodplain_mesh
   )
   
   # Create coupling junction
   coupling_junction = Junction(
       name="river_floodplain_coupling",
       junction_type="lateral_weir",
       parameters={
           "weir_coefficient": 1.7,
           "weir_length": 200.0,
           "weir_elevation": 105.0
       }
   )
   
   # Set up coupled simulation controller
   controller = SimulationController()
   controller.add_component(river_model)
   controller.add_component(floodplain_model)
   controller.add_component(coupling_junction)
   
   # Define connections
   controller.add_connection("main_river", "river_floodplain_coupling")
   controller.add_connection("river_floodplain_coupling", "floodplain")
   
   # Run coupled simulation
   simulation_time = 3600 * 12  # 12 hours
   dt = 60.0  # 1-minute time step
   
   for t in range(0, simulation_time, int(dt)):
       # Set upstream boundary condition
       upstream_flow = flood_hydrograph(t)
       inputs = {"main_river": {"upstream_flow": upstream_flow}}
       
       # Step coupled system
       controller.step(inputs, dt)
       
       # Get results
       river_levels = river_model.get_water_levels()
       floodplain_depths = floodplain_model.get_water_depths()
       
       # Check for overbank flow
       if np.any(floodplain_depths > 0.1):
           overbank_volume = np.sum(floodplain_depths * floodplain_mesh.cell_areas)
           print(f"Time: {t/3600:.1f}h, Overbank volume: {overbank_volume/1000:.1f} ML")

Advanced Features
-----------------

Adaptive Mesh Refinement
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.mesh import AdaptiveMesh
   from model_2d.refinement import GradientRefinement
   
   # Create adaptive mesh
   adaptive_mesh = AdaptiveMesh.from_base_mesh(base_mesh)
   
   # Set refinement criteria
   refinement_criteria = GradientRefinement(
       variable="depth",
       threshold=0.1,  # Refine where depth gradient > 0.1 m/m
       max_levels=3    # Maximum 3 refinement levels
   )
   
   adaptive_mesh.set_refinement_criteria(refinement_criteria)
   
   # Create model with adaptive mesh
   adaptive_model = Model2D(
       name="adaptive_flood",
       mesh=adaptive_mesh
   )
   
   # Run with mesh adaptation
   for t in range(0, simulation_time, int(dt)):
       adaptive_model.step({}, dt)
       
       # Adapt mesh every 10 time steps
       if t % (10 * dt) == 0:
           adaptive_mesh.adapt()
           print(f"Mesh adapted: {adaptive_mesh.num_cells} cells")

GPU Acceleration
~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.solver import CUDASolver
   import cupy as cp
   
   # Check GPU availability
   if cp.cuda.is_available():
       # Create GPU-accelerated solver
       gpu_solver = CUDASolver(
           device_id=0,
           memory_pool_size="4GB"
       )
       
       # Create model with GPU solver
       gpu_model = Model2D(
           name="gpu_flood_model",
           mesh=large_mesh,
           solver=gpu_solver
       )
       
       # Transfer data to GPU
       gpu_model.transfer_to_gpu()
       
       # Run GPU simulation
       for t in range(0, simulation_time, int(dt)):
           gpu_model.step({}, dt)
           
           # Transfer results back to CPU periodically
           if t % 600 == 0:
               depths = gpu_model.get_water_depths_cpu()
               print(f"Time: {t/60:.0f}min, Max depth: {np.max(depths):.2f}m")
   else:
       print("GPU not available, using CPU solver")

Parallel Processing
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.parallel import DomainDecomposition
   import mpi4py.MPI as MPI
   
   # Initialize MPI
   comm = MPI.COMM_WORLD
   rank = comm.Get_rank()
   size = comm.Get_size()
   
   # Domain decomposition
   decomposer = DomainDecomposition(
       mesh=large_mesh,
       num_domains=size,
       method="metis"  # Use METIS partitioning
   )
   
   # Get local domain for this process
   local_mesh = decomposer.get_local_mesh(rank)
   
   # Create local model
   local_model = Model2D(
       name=f"domain_{rank}",
       mesh=local_mesh,
       communicator=comm
   )
   
   # Run parallel simulation
   for t in range(0, simulation_time, int(dt)):
       # Exchange boundary data
       local_model.exchange_boundaries()
       
       # Step local domain
       local_model.step({}, dt)
       
       # Synchronize
       comm.Barrier()
       
       if rank == 0 and t % 600 == 0:
           print(f"Time: {t/60:.0f}min (parallel simulation)")

Wetting and Drying
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.wetting_drying import WettingDryingModule
   
   # Configure wetting and drying
   wd_module = WettingDryingModule(
       dry_threshold=0.001,    # 1mm dry threshold
       wet_threshold=0.002,    # 2mm wet threshold
       method="volume_conservative"
   )
   
   # Add to model
   model.add_module(wd_module)
   
   # The module automatically handles:
   # - Cell activation/deactivation
   # - Mass conservation during wetting/drying
   # - Numerical stability near dry boundaries

Configuration and Parameters
----------------------------

Solver Parameters
~~~~~~~~~~~~~~~~~

**Time Step Control:**

.. code-block:: python

   solver_config = {
       'time_scheme': 'explicit',      # or 'implicit'
       'cfl_number': 0.8,             # Courant number
       'adaptive_dt': True,           # Adaptive time stepping
       'min_dt': 0.1,                 # Minimum time step (s)
       'max_dt': 60.0,                # Maximum time step (s)
   }

**Spatial Discretization:**

.. code-block:: python

   mesh_config = {
       'element_type': 'triangular',   # or 'quadrilateral'
       'max_area': 100.0,             # Maximum element area (m²)
       'min_angle': 20.0,             # Minimum angle (degrees)
       'boundary_refinement': True,    # Refine near boundaries
   }

**Numerical Parameters:**

.. code-block:: python

   numerical_config = {
       'flux_scheme': 'hll',          # Riemann solver
       'slope_limiter': 'minmod',     # Slope limiter
       'friction_scheme': 'implicit', # Friction treatment
       'turbulence_model': 'smagorinsky',  # Turbulence model
   }

Mesh Generation
~~~~~~~~~~~~~~~

**From GIS Data:**

.. code-block:: python

   from model_2d.mesh import MeshGenerator
   
   # Generate mesh from GIS data
   generator = MeshGenerator()
   
   mesh = generator.from_shapefile(
       boundary_file="domain_boundary.shp",
       elevation_file="elevation.tif",
       max_area=50.0,
       min_angle=25.0
   )

**Structured Mesh:**

.. code-block:: python

   # Create structured rectangular mesh
   structured_mesh = QuadrilateralMesh.create_rectangle(
       x_min=0, x_max=1000,
       y_min=0, y_max=500,
       nx=100, ny=50,
       element_type='quadrilateral'
   )

**Unstructured Mesh:**

.. code-block:: python

   # Create unstructured triangular mesh
   unstructured_mesh = TriangularMesh.create_from_points(
       points=boundary_points,
       holes=island_points,
       max_area=25.0
   )

Boundary Conditions
~~~~~~~~~~~~~~~~~~~

**Inflow Boundaries:**

.. code-block:: python

   # Discharge boundary
   model.set_inflow_bc(
       boundary_edges=inflow_edges,
       discharge_series=discharge_function
   )
   
   # Velocity boundary
   model.set_velocity_bc(
       boundary_edges=velocity_edges,
       velocity_x=u_function,
       velocity_y=v_function
   )

**Outflow Boundaries:**

.. code-block:: python

   # Free outflow
   model.set_outflow_bc(
       boundary_edges=outflow_edges,
       condition_type="free"
   )
   
   # Fixed level
   model.set_level_bc(
       boundary_edges=level_edges,
       level_series=level_function
   )

**Wall Boundaries:**

.. code-block:: python

   # No-slip walls
   model.set_wall_bc(
       boundary_edges=wall_edges,
       condition_type="no_slip"
   )
   
   # Slip walls
   model.set_wall_bc(
       boundary_edges=slip_edges,
       condition_type="slip"
   )

Performance Optimization
------------------------

Memory Management
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Optimize memory usage
   model.set_memory_options({
       'store_history': False,        # Don't store time history
       'output_frequency': 60,        # Output every 60 time steps
       'compress_output': True,       # Compress output files
       'use_single_precision': True   # Use float32 instead of float64
   })

Computational Efficiency
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Performance optimizations
   model.set_performance_options({
       'vectorization': True,         # Use vectorized operations
       'parallel_assembly': True,     # Parallel matrix assembly
       'cache_geometry': True,        # Cache geometric calculations
       'optimize_bandwidth': True     # Optimize matrix bandwidth
   })

Error Handling and Debugging
----------------------------

Common Issues
~~~~~~~~~~~~~

**Numerical Instability:**

- Reduce time step size
- Check mesh quality
- Verify boundary conditions
- Use implicit time stepping

**Mass Conservation:**

- Check boundary condition consistency
- Monitor mass balance errors
- Use conservative flux schemes
- Verify wetting/drying treatment

**Convergence Problems:**

- Increase solver iterations
- Improve initial conditions
- Check for negative depths
- Use adaptive time stepping

Debugging Tools
~~~~~~~~~~~~~~~

.. code-block:: python

   # Enable debugging
   model.set_debug_options({
       'check_mass_balance': True,    # Check mass conservation
       'monitor_cfl': True,           # Monitor CFL condition
       'detect_instability': True,    # Detect numerical instability
       'log_solver_info': True        # Log solver information
   })
   
   # Visualize mesh and results
   model.plot_mesh()
   model.plot_water_depths()
   model.plot_velocity_field()
   model.plot_mass_balance()

Validation and Verification
---------------------------

Analytical Test Cases
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.validation import AnalyticalTests
   
   # Thacker's planar beach test
   thacker_test = AnalyticalTests.thacker_planar_beach()
   model_result = model.run_test_case(thacker_test)
   
   # Compare with analytical solution
   analytical_solution = thacker_test.get_analytical_solution()
   error = model_result.compare_with_analytical(analytical_solution)
   print(f"L2 error: {error['l2_norm']:.6f}")

Benchmark Problems
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from model_2d.benchmarks import Benchmarks
   
   # SWASHES dam break benchmark
   dam_break_benchmark = Benchmarks.swashes_dam_break()
   benchmark_result = model.run_benchmark(dam_break_benchmark)
   
   # Evaluate against reference data
   score = dam_break_benchmark.evaluate(benchmark_result)
   print(f"Benchmark score: {score:.3f}")

Output and Visualization
------------------------

File Formats
~~~~~~~~~~~~

.. code-block:: python

   # VTK format (for ParaView)
   model.export_vtk("results.vtk")
   
   # NetCDF format
   model.export_netcdf("results.nc")
   
   # GeoTIFF format
   model.export_geotiff("flood_depths.tif")
   
   # CSV format
   model.export_csv("time_series.csv")

Visualization
~~~~~~~~~~~~~

.. code-block:: python

   import matplotlib.pyplot as plt
   from model_2d.visualization import FloodPlotter
   
   # Create flood visualization
   plotter = FloodPlotter(model)
   
   # Plot flood depths
   fig, ax = plotter.plot_flood_depths(
       time_index=-1,  # Final time step
       colormap='Blues',
       show_mesh=False
   )
   plt.savefig('flood_depths.png', dpi=300)
   
   # Plot velocity vectors
   fig, ax = plotter.plot_velocity_field(
       time_index=-1,
       scale=10,
       show_magnitude=True
   )
   plt.savefig('velocity_field.png', dpi=300)
   
   # Create animation
   animation = plotter.create_animation(
       variable='depth',
       output_file='flood_animation.mp4',
       fps=10
   )