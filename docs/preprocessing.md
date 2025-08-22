# Data Preprocessing and Validation

To ensure the quality of model inputs and to generate valuable derived data, the framework includes a powerful data preprocessing pipeline that is executed before the main simulation run. This pipeline is configured via the `preprocessing` section in your `config.yaml` file.

## Runoff Coefficient Calculation

This tool provides a quick and effective way to validate the consistency of your rainfall and streamflow data. It calculates the runoff coefficient for the entire period of overlapping data. An outputted coefficient that is negative or greater than 1.0 is a strong indication of issues with the data, such as mismatched units, incorrect catchment area, or significant data quality problems.

### Configuration
To enable this check, add a `runoff_coefficient` section to the `preprocessing` block in your `config.yaml`:

```yaml
preprocessing:
  runoff_coefficient:
    rainfall_input: "precip_areal"  # Name of the rainfall data source
    flow_input: "observed_flow"     # Name of the streamflow data source
    catchment_area_km2: 500.0       # Area of the catchment in square kilometers
```

### Parameters:
- `rainfall_input` (required): The name of the data source containing the rainfall time series. This can be an initial input or the output of a previous processing step (like `areal_precipitation`).
- `flow_input` (required): The name of the data source for the observed streamflow.
- `catchment_area_km2` (required): The catchment area in km^2, used for converting rainfall depth to volume.

### Output:
This tool prints the calculated total volumes and the resulting runoff coefficient to the console, along with a warning if the value is outside the plausible range of [0, 1].

## Baseflow Separation

This tool separates a total streamflow hydrograph into two components: quick flow (direct runoff) and baseflow. This is useful for more detailed model analysis and calibration. The implementation uses the robust, three-pass Lyne-Hollick digital filter.

### Configuration
To use this feature, add a `baseflow_separation` section to the `preprocessing` block:

```yaml
preprocessing:
  baseflow_separation:
    flow_input: "observed_flow"
    output_baseflow: "flow_base"     # Name for the new baseflow data source
    output_quickflow: "flow_quick"   # Name for the new quickflow data source
    parameters:
      alpha: 0.925
      passes: 3
      n_reflect: 10
```

### Parameters:
- `flow_input` (required): The name of the streamflow data source to be separated.
- `output_baseflow` (required): The name to be given to the new baseflow time series. This new data source can be used by other components.
- `output_quickflow` (required): The name to be given to the new quick flow time series.
- `parameters` (optional): A dictionary of parameters for the Lyne-Hollick filter.
    - `alpha` (optional, default: 0.925): The filter parameter.
    - `passes` (optional, default: 3): The number of filter passes. Must be an odd integer.
    - `n_reflect` (optional, default: 30): The number of data points to reflect at the ends of the series to reduce artifacts.

## Chaining Operations

The preprocessing pipeline is designed to be flexible. The `output_name` of one step (e.g., `areal_precipitation`) can be used as the `input_name` or `rainfall_input` of a subsequent step. This allows you to create a custom, chained workflow for your data preparation.

## Complete Example
For a complete, runnable demonstration of these features, please see the example located in the `examples/preprocessing_example/` directory.
