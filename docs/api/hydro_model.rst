hydro_model package
===================

.. automodule:: hydro_model
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

hydro_model.runoff module
-------------------------

.. automodule:: hydro_model.runoff
   :members:
   :undoc-members:
   :show-inheritance:

hydro_model.routing module
--------------------------

.. automodule:: hydro_model.routing
   :members:
   :undoc-members:
   :show-inheritance:

hydro_model.evapotranspiration module
-------------------------------------

.. automodule:: hydro_model.evapotranspiration
   :members:
   :undoc-members:
   :show-inheritance:

hydro_model.infiltration module
-------------------------------

.. automodule:: hydro_model.infiltration
   :members:
   :undoc-members:
   :show-inheritance:

hydro_model.snow module
-----------------------

.. automodule:: hydro_model.snow
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The hydro_model package provides hydrological modeling components for the Hydrology Framework.
It includes modules for various hydrological processes:

* **Runoff Generation**: Surface runoff calculation using various methods
* **Routing**: Flow routing through channels and catchments
* **Evapotranspiration**: ET calculation using different approaches
* **Infiltration**: Soil infiltration modeling
* **Snow**: Snow accumulation and melt processes

Key Classes and Functions
-------------------------

Runoff Module
~~~~~~~~~~~~~

.. autoclass:: hydro_model.runoff.SCSCurveNumberModule
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.runoff.RationalMethodModule
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.runoff.GreenAmptModule
   :members:
   :special-members: __init__

Routing Module
~~~~~~~~~~~~~~

.. autoclass:: hydro_model.routing.SimpleRouting
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.routing.MuskingumRouting
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.routing.UnitHydrographRouting
   :members:
   :special-members: __init__

Evapotranspiration Module
~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: hydro_model.evapotranspiration.PenmanMonteithET
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.evapotranspiration.HargreavesSamaniET
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.evapotranspiration.PriestleyTaylorET
   :members:
   :special-members: __init__

Infiltration Module
~~~~~~~~~~~~~~~~~~~

.. autoclass:: hydro_model.infiltration.HortonInfiltration
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.infiltration.PhilipInfiltration
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.infiltration.GreenAmptInfiltration
   :members:
   :special-members: __init__

Snow Module
~~~~~~~~~~~

.. autoclass:: hydro_model.snow.TemperatureIndexSnow
   :members:
   :special-members: __init__

.. autoclass:: hydro_model.snow.EnergyBalanceSnow
   :members:
   :special-members: __init__

Usage Examples
--------------

Basic Runoff Calculation
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydro_model.runoff import SCSCurveNumberModule
   
   # Create runoff module
   runoff = SCSCurveNumberModule(
       curve_number=75,
       area_km2=10.0,
       initial_abstraction_ratio=0.2
   )
   
   # Calculate runoff for rainfall event
   runoff_rate = runoff.run(rainfall=25.0, dt=3600)
   print(f"Runoff rate: {runoff_rate:.2f} m³/s")

Flow Routing
~~~~~~~~~~~~

.. code-block:: python

   from hydro_model.routing import MuskingumRouting
   
   # Create routing module
   routing = MuskingumRouting(
       k=2.0,  # Storage coefficient (hours)
       x=0.2   # Weighting factor
   )
   
   # Route hydrograph
   inflow = [10, 20, 30, 25, 15, 10, 5]
   outflow = []
   
   for q_in in inflow:
       q_out = routing.run(inflow=q_in, dt=3600)
       outflow.append(q_out)

Evapotranspiration Calculation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydro_model.evapotranspiration import PenmanMonteithET
   
   # Create ET module
   et_module = PenmanMonteithET(
       crop_coefficient=1.0,
       surface_resistance=70.0,
       aerodynamic_resistance=208.0
   )
   
   # Calculate ET
   weather_data = {
       'temperature': 25.0,  # °C
       'humidity': 60.0,     # %
       'wind_speed': 2.0,    # m/s
       'solar_radiation': 20.0  # MJ/m²/day
   }
   
   et_rate = et_module.run(weather_data, dt=86400)
   print(f"ET rate: {et_rate:.2f} mm/day")

Snow Modeling
~~~~~~~~~~~~~

.. code-block:: python

   from hydro_model.snow import TemperatureIndexSnow
   
   # Create snow module
   snow = TemperatureIndexSnow(
       degree_day_factor=3.0,  # mm/°C/day
       base_temperature=0.0,   # °C
       initial_swe=50.0        # mm
   )
   
   # Simulate snow accumulation and melt
   temperature = [-5, -2, 0, 2, 5, 3, 1, -1]
   precipitation = [10, 5, 0, 0, 0, 2, 8, 15]
   
   for temp, precip in zip(temperature, precipitation):
       result = snow.run(
           temperature=temp,
           precipitation=precip,
           dt=86400
       )
       print(f"Temp: {temp:3.0f}°C, Precip: {precip:2.0f}mm, "
             f"SWE: {result['swe']:5.1f}mm, Melt: {result['melt']:4.1f}mm")

Integrated Catchment Model
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydro_model.runoff import SCSCurveNumberModule
   from hydro_model.routing import SimpleRouting
   from hydro_model.evapotranspiration import HargreavesSamaniET
   from hydro_model.snow import TemperatureIndexSnow
   
   # Create integrated catchment model
   class CatchmentModel:
       def __init__(self):
           self.snow = TemperatureIndexSnow(
               degree_day_factor=3.0,
               base_temperature=0.0
           )
           
           self.et = HargreavesSamaniET(
               latitude=45.0,
               crop_coefficient=1.0
           )
           
           self.runoff = SCSCurveNumberModule(
               curve_number=75,
               area_km2=25.0
           )
           
           self.routing = SimpleRouting(
               k_q=0.5,
               k_s=0.1
           )
       
       def run_timestep(self, weather_data, dt):
           # Snow processes
           snow_result = self.snow.run(
               temperature=weather_data['temperature'],
               precipitation=weather_data['precipitation'],
               dt=dt
           )
           
           # Evapotranspiration
           et_rate = self.et.run(weather_data, dt)
           
           # Effective precipitation (rain + snowmelt - ET)
           effective_precip = (
               weather_data['precipitation'] + 
               snow_result['melt'] - 
               et_rate
           )
           effective_precip = max(0, effective_precip)
           
           # Runoff generation
           runoff_rate = self.runoff.run(
               rainfall=effective_precip,
               dt=dt
           )
           
           # Flow routing
           routed_flow = self.routing.run(
               inflow=runoff_rate,
               dt=dt
           )
           
           return {
               'snow_swe': snow_result['swe'],
               'snowmelt': snow_result['melt'],
               'et': et_rate,
               'effective_precipitation': effective_precip,
               'runoff': runoff_rate,
               'streamflow': routed_flow
           }
   
   # Usage
   model = CatchmentModel()
   
   # Daily simulation
   daily_weather = [
       {'temperature': 5, 'precipitation': 10, 'humidity': 70},
       {'temperature': 8, 'precipitation': 0, 'humidity': 65},
       {'temperature': 12, 'precipitation': 5, 'humidity': 60},
   ]
   
   for day, weather in enumerate(daily_weather, 1):
       result = model.run_timestep(weather, dt=86400)
       print(f"Day {day}: Streamflow = {result['streamflow']:.2f} m³/s")

Configuration and Parameters
----------------------------

Model Parameters
~~~~~~~~~~~~~~~~

Each module accepts various parameters that control its behavior:

**SCS Curve Number Parameters:**

- ``curve_number``: SCS curve number (30-100)
- ``area_km2``: Catchment area in km²
- ``initial_abstraction_ratio``: Initial abstraction ratio (typically 0.2)

**Muskingum Routing Parameters:**

- ``k``: Storage coefficient (hours)
- ``x``: Weighting factor (0-0.5)
- ``dt``: Time step (seconds)

**Penman-Monteith ET Parameters:**

- ``crop_coefficient``: Crop coefficient (0.5-1.5)
- ``surface_resistance``: Surface resistance (s/m)
- ``aerodynamic_resistance``: Aerodynamic resistance (s/m)

Parameter Sensitivity
~~~~~~~~~~~~~~~~~~~~~

Some parameters have significant impact on model results:

- **Curve Number**: Highly sensitive, affects runoff volume
- **Routing Coefficients**: Affect timing and peak flows
- **ET Parameters**: Important for water balance
- **Snow Parameters**: Critical in snow-dominated catchments

Calibration Guidelines
~~~~~~~~~~~~~~~~~~~~~~

For model calibration:

1. **Start with literature values** for physical parameters
2. **Use observed data** for calibration when available
3. **Consider parameter uncertainty** and ranges
4. **Validate with independent data** sets
5. **Document calibration process** and assumptions

Performance Considerations
--------------------------

Optimization Tips
~~~~~~~~~~~~~~~~~

- **Vectorize operations** when processing multiple time steps
- **Use appropriate time steps** for different processes
- **Cache intermediate results** when possible
- **Profile code** to identify bottlenecks

Memory Management
~~~~~~~~~~~~~~~~~

- **Limit state storage** to essential variables
- **Use efficient data structures** (NumPy arrays)
- **Clear unused variables** in long simulations
- **Monitor memory usage** for large catchments

Error Handling
--------------

Common Issues
~~~~~~~~~~~~~

- **Invalid parameters**: Check parameter ranges and units
- **Missing data**: Handle gaps in input time series
- **Numerical instability**: Use appropriate time steps
- **Unit mismatches**: Ensure consistent units throughout

Debugging Tips
~~~~~~~~~~~~~~

- **Enable logging** to track model behavior
- **Check intermediate results** at each step
- **Validate inputs** before processing
- **Use test cases** with known solutions