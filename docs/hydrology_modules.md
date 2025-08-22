# Hydrology Modules

This document details the various process-based modules available for use within the `HydrologicalModel` component.

## Runoff Modules

Runoff modules are the core of the hydrological model, calculating the amount of runoff generated from rainfall (or liquid water from a snowmelt module).

### `SimpleRunoffModule`
A basic conceptual model with parameters for maximum soil storage (`S_max`) and a loss coefficient (`c_loss`).

### `SCSCurveNumberModule`
An empirical model based on the widely-used SCS Curve Number method. Its primary parameter is `CN`.

### `XinanjiangRunoffModule`
A complex conceptual model popular in humid regions, with many parameters (K, B, IM, etc.).

### `HymodRunoffModule`
A popular 5-parameter conceptual model (`cmax`, `bexp`, `alpha`, `ks`, `kq`).

## Snowmelt Modules

Snowmelt modules can be optionally included in a `HydrologicalModel`. They act as a pre-processor for the runoff module, taking in total precipitation and temperature, and outputting the amount of liquid water (rain + snowmelt) available for runoff generation.

### `SnowmeltRunoffModule`
A simple and effective Temperature-Index (or Degree-Day) model.

#### Functionality
- **Precipitation Partitioning:** Determines if precipitation falls as rain or snow based on a `base_temperature`.
- **Snow Accumulation:** Adds new snowfall to the Snow Water Equivalent (SWE) state variable.
- **Snowmelt Calculation:** Calculates the amount of melt based on the temperature above the base temperature and a `degree_day_factor`.

#### Configuration Example
The `snowmelt_module` is defined as a sub-component within a `HydrologicalModel` in your `config.yaml`:

```yaml
components:
  - name: "SnowyCatchment"
    type: HydrologicalModel
    parameters:
      # This model has two sub-modules: one for snow, one for runoff
      snowmelt_module:
        type: SnowmeltRunoffModule
        parameters:
          degree_day_factor: 4.5 # mm/day/°C
          base_temperature: 0.5 # °C

      runoff_module:
        type: SimpleRunoffModule
        parameters:
          S_max: 100.0
          c_loss: 0.1
```

#### Required Inputs
When a `HydrologicalModel` includes a `snowmelt_module`, it requires a `temperature` time series in its `global_inputs`, in addition to `rainfall` (which represents total precipitation).

#### Example
For a complete, runnable demonstration, please see the example located in the `examples/snowmelt_example/` directory.
