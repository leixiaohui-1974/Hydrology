# Analysis Tools

This section describes standalone scripts located in the `analysis/` directory that can be used for post-processing and visualizing model results and data.

## Interpolation Uncertainty Plotter

**Script:** `analysis/plot_interpolation_uncertainty.py`

### Purpose

When using the `kriging` method for areal precipitation, the model calculates both the mean interpolated rainfall and the variance of the estimation. This variance is a measure of the uncertainty of the interpolation, which is typically higher in areas far from rain gauges. This tool allows you to visualize this uncertainty.

### How to Use

The script is run from the command line and takes a single argument: the path to a configuration file that has been set up to use the `kriging` interpolation method.

1.  **Ensure your `config.yaml` is configured for Kriging:**
    ```yaml
    areal_precipitation:
      input_name: "rainfall"
      output_name: "precip_areal"
      # ... other required parameters ...
      method: "kriging"
    ```

2.  **Run the script from the project's root directory:**
    ```bash
    python3 analysis/plot_interpolation_uncertainty.py path/to/your/config.yaml
    ```

### Output

The script will:
1.  Run the data loading and areal precipitation steps defined in your config file. This will generate the mean rainfall data source (e.g., `precip_areal`) and the variance data source (e.g., `precip_areal_variance`).
2.  Read the variance data.
3.  Generate and save a plot named `interpolation_variance_plot.png` in the same directory as your config file. This plot shows the mean estimation variance for each sub-basin over time.
