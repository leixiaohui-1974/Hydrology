# Areal Precipitation Calculation

The framework now includes a powerful module for calculating areal precipitation from point gauge data. This allows for more spatially accurate rainfall inputs to the hydrological models, moving beyond a simple single-station-per-basin approach.

The module supports two widely-used interpolation methods:
- **Inverse Distance Weighting (IDW)**
- **Thiessen Polygons**

## How it Works

The areal precipitation calculation is handled as a pre-processing step during the simulation setup. When a special `areal_precipitation` section is detected in your `config.yaml` file, the `ConfigParser` automatically invokes the `ArealPrecipitation` module.

The workflow is as follows:
1.  The module reads the locations of your rain gauges.
2.  It reads the polygon geometries of your sub-basins.
3.  It loads the multi-station raw rainfall time series data.
4.  It performs a data cleaning step to handle missing values (via linear interpolation) and remove negatives.
5.  Using the specified method (IDW or Thiessen), it calculates a unique, spatially-averaged rainfall time series for each sub-basin.
6.  These new time series are then passed to the corresponding hydrological model components for the simulation run.

## Configuration

To enable this feature, add an `areal_precipitation` section to your `config.yaml` file.

```yaml
# NEW: Configure Areal Precipitation
areal_precipitation:
  subbasins_shapefile: "path/to/your/subbasins.shp"
  rain_gauges_file: "path/to/your/rain_gauges.csv"
  method: "idw" # or "thiessen"
  parameters:
    power: 2 # Optional: specific to the 'idw' method
```

### Parameters:
- `subbasins_shapefile` (required): The path to the shapefile containing your sub-basin polygons. The path is relative to the location of the `config.yaml` file.
- `rain_gauges_file` (required): The path to the CSV file containing your rain gauge locations.
- `method` (required): The interpolation method to use. Can be either `"idw"` or `"thiessen"`.
- `parameters` (optional): A dictionary of additional parameters for the chosen method.
    - For `idw`, you can specify `power`, which is the exponent used in the weighting calculation (defaults to 2).
    - For `thiessen`, you can specify an optional `cache_file` (e.g., `"thiessen_weights.json"`). If provided, the calculated Thiessen polygon weights will be saved to this file on the first run. Subsequent runs will load the weights directly from the cache, significantly improving performance.

## Required Data Formats

### 1. Rain Gauges File
This must be a CSV file with the following columns: `station_id`, `x`, and `y`.

- `station_id`: The identifier for the gauge. **This must exactly match the corresponding column name in your rainfall data file.**
- `x`, `y`: The spatial coordinates of the gauge.

Example (`rain_gauges.csv`):
```csv
station_id,x,y
rainfall_1,500000,5060000
rainfall_2,510000,5065000
rainfall_3,505000,5055000
```

### 2. Sub-basins Shapefile
This must be a standard polygon shapefile. The module uses the shapefile's index or a specified ID column to identify each sub-basin. For the framework to correctly map the calculated rainfall to the model components, **the name of each hydrological model component in your `config.yaml` must match the ID of the corresponding sub-basin in the shapefile's attribute table.**

### 3. Rainfall Data File
This is a CSV file where the first column is the date/time, and subsequent columns contain the rainfall measurements for each gauge.

- The index column must be a parsable date/time.
- The header of each rainfall column must match a `station_id` in your `rain_gauges.csv` file.

Example (`rainfall.csv`):
```csv
date,rainfall_1,rainfall_2,rainfall_3
2023-01-01,0,0,0
2023-01-02,5,4,3
2023-01-03,15,12,10
...
```

## Complete Example
For a complete, runnable demonstration of this feature, please see the example located in the `examples/areal_precipitation_example/` directory. It includes a working configuration file, all necessary data, and a script to run the simulation and plot the results.
