preprocessing package
=====================

.. automodule:: preprocessing
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

preprocessing.baseflow_separation module
----------------------------------------

.. automodule:: preprocessing.baseflow_separation
   :members:
   :undoc-members:
   :show-inheritance:

preprocessing.runoff_analysis module
------------------------------------

.. automodule:: preprocessing.runoff_analysis
   :members:
   :undoc-members:
   :show-inheritance:

preprocessing.data_quality module
---------------------------------

.. automodule:: preprocessing.data_quality
   :members:
   :undoc-members:
   :show-inheritance:

preprocessing.time_series module
--------------------------------

.. automodule:: preprocessing.time_series
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The preprocessing package provides comprehensive data preprocessing capabilities for hydrological analysis.
It includes tools for data cleaning, quality control, baseflow separation, runoff analysis, and time series processing.

Key Features
------------

* **Data Quality Control**: Missing data detection, outlier identification, and data validation
* **Baseflow Separation**: Multiple algorithms for separating baseflow from total streamflow
* **Runoff Analysis**: Calculation of runoff coefficients, peak flow analysis, and hydrograph analysis
* **Time Series Processing**: Resampling, interpolation, smoothing, and trend analysis
* **Statistical Analysis**: Descriptive statistics, frequency analysis, and correlation analysis
* **Data Transformation**: Normalization, standardization, and log transformations
* **Gap Filling**: Multiple methods for filling missing data

Key Functions
-------------

lyne_hollick_filter Function
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autofunction:: preprocessing.baseflow_separation.lyne_hollick_filter

calculate_runoff_coefficient Function
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autofunction:: preprocessing.runoff_analysis.calculate_runoff_coefficient

Usage Examples
--------------

Baseflow Separation
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.baseflow_separation import lyne_hollick_filter
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   
   # Load streamflow data
   flow_data = pd.read_csv("streamflow_data.csv", parse_dates=['date'])
   flow_data.set_index('date', inplace=True)
   
   # Apply Lyne-Hollick filter for baseflow separation
   baseflow_result = lyne_hollick_filter(
       flow_series=flow_data,
       alpha=0.925,  # Filter parameter (0.9-0.95 typical)
       passes=3,     # Number of filter passes
       n_reflect=30  # Reflection points
   )
   
   # Extract results
   total_flow = baseflow_result['flow']
   baseflow = baseflow_result['baseflow']
   quickflow = baseflow_result['quickflow']
   
   # Calculate baseflow index
   baseflow_index = baseflow.sum() / total_flow.sum()
   print(f"Baseflow Index: {baseflow_index:.3f}")
   
   # Plot results
   fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
   
   # Plot hydrograph separation
   ax1.plot(total_flow.index, total_flow.values, 'b-', label='Total Flow', alpha=0.7)
   ax1.plot(baseflow.index, baseflow.values, 'g-', label='Baseflow', linewidth=2)
   ax1.fill_between(baseflow.index, 0, baseflow.values, alpha=0.3, color='green')
   ax1.fill_between(quickflow.index, baseflow.values, total_flow.values, 
                    alpha=0.3, color='blue', label='Quickflow')
   ax1.set_ylabel('Flow (m³/s)')
   ax1.set_title('Baseflow Separation using Lyne-Hollick Filter')
   ax1.legend()
   ax1.grid(True, alpha=0.3)
   
   # Plot baseflow index over time (monthly)
   monthly_bf_index = baseflow.resample('M').sum() / total_flow.resample('M').sum()
   ax2.plot(monthly_bf_index.index, monthly_bf_index.values, 'ro-', markersize=4)
   ax2.axhline(y=baseflow_index, color='r', linestyle='--', 
               label=f'Overall BFI: {baseflow_index:.3f}')
   ax2.set_ylabel('Baseflow Index')
   ax2.set_xlabel('Date')
   ax2.set_title('Monthly Baseflow Index')
   ax2.legend()
   ax2.grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()
   
   # Compare different alpha values
   alpha_values = [0.90, 0.925, 0.95, 0.975]
   bf_indices = []
   
   for alpha in alpha_values:
       result = lyne_hollick_filter(flow_data, alpha=alpha, passes=3)
       bf_index = result['baseflow'].sum() / result['flow'].sum()
       bf_indices.append(bf_index)
   
   # Plot sensitivity analysis
   plt.figure(figsize=(8, 6))
   plt.plot(alpha_values, bf_indices, 'bo-', markersize=8)
   plt.xlabel('Alpha Parameter')
   plt.ylabel('Baseflow Index')
   plt.title('Sensitivity of Baseflow Index to Alpha Parameter')
   plt.grid(True, alpha=0.3)
   for i, (alpha, bfi) in enumerate(zip(alpha_values, bf_indices)):
       plt.annotate(f'{bfi:.3f}', (alpha, bfi), 
                   textcoords="offset points", xytext=(0,10), ha='center')
   plt.show()

Runoff Analysis
~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.runoff_analysis import calculate_runoff_coefficient
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   
   # Load rainfall and streamflow data
   rainfall_data = pd.read_csv("rainfall_data.csv", parse_dates=['date'])
   rainfall_data.set_index('date', inplace=True)
   
   flow_data = pd.read_csv("streamflow_data.csv", parse_dates=['date'])
   flow_data.set_index('date', inplace=True)
   
   # Catchment area in km²
   catchment_area = 125.5
   
   # Calculate runoff coefficient
   runoff_coeff = calculate_runoff_coefficient(
       rainfall_series=rainfall_data['rainfall'],
       flow_series=flow_data['flow'],
       catchment_area_km2=catchment_area
   )
   
   if runoff_coeff is not None:
       print(f"Runoff Coefficient: {runoff_coeff:.3f}")
       print(f"This means {runoff_coeff*100:.1f}% of rainfall becomes runoff")
   else:
       print("Could not calculate runoff coefficient (insufficient data)")
   
   # Calculate monthly runoff coefficients
   monthly_coeffs = []
   monthly_dates = []
   
   for year in range(rainfall_data.index.year.min(), rainfall_data.index.year.max() + 1):
       for month in range(1, 13):
           # Get monthly data
           start_date = pd.Timestamp(year, month, 1)
           if month == 12:
               end_date = pd.Timestamp(year + 1, 1, 1)
           else:
               end_date = pd.Timestamp(year, month + 1, 1)
           
           monthly_rainfall = rainfall_data.loc[start_date:end_date-pd.Timedelta(days=1)]
           monthly_flow = flow_data.loc[start_date:end_date-pd.Timedelta(days=1)]
           
           if len(monthly_rainfall) > 0 and len(monthly_flow) > 0:
               monthly_coeff = calculate_runoff_coefficient(
                   rainfall_series=monthly_rainfall['rainfall'],
                   flow_series=monthly_flow['flow'],
                   catchment_area_km2=catchment_area
               )
               
               if monthly_coeff is not None:
                   monthly_coeffs.append(monthly_coeff)
                   monthly_dates.append(start_date)
   
   # Plot monthly runoff coefficients
   if monthly_coeffs:
       plt.figure(figsize=(12, 6))
       plt.plot(monthly_dates, monthly_coeffs, 'bo-', markersize=4, alpha=0.7)
       plt.axhline(y=runoff_coeff, color='r', linestyle='--', 
                   label=f'Overall: {runoff_coeff:.3f}')
       plt.xlabel('Date')
       plt.ylabel('Runoff Coefficient')
       plt.title('Monthly Runoff Coefficients')
       plt.legend()
       plt.grid(True, alpha=0.3)
       plt.xticks(rotation=45)
       plt.tight_layout()
       plt.show()
       
       # Seasonal analysis
       monthly_df = pd.DataFrame({
           'date': monthly_dates,
           'runoff_coeff': monthly_coeffs
       })
       monthly_df['month'] = monthly_df['date'].dt.month
       
       seasonal_stats = monthly_df.groupby('month')['runoff_coeff'].agg([
           'mean', 'std', 'min', 'max', 'count'
       ])
       
       print("\nSeasonal Runoff Coefficient Statistics:")
       print(seasonal_stats)
       
       # Plot seasonal variation
       plt.figure(figsize=(10, 6))
       months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
       
       plt.errorbar(range(1, 13), seasonal_stats['mean'], 
                   yerr=seasonal_stats['std'], 
                   fmt='o-', capsize=5, capthick=2, markersize=6)
       plt.xlabel('Month')
       plt.ylabel('Runoff Coefficient')
       plt.title('Seasonal Variation in Runoff Coefficient')
       plt.xticks(range(1, 13), months)
       plt.grid(True, alpha=0.3)
       plt.tight_layout()
       plt.show()

Data Quality Control
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.data_quality import (
       detect_outliers, fill_missing_data, validate_data_consistency
   )
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   
   # Load data with potential quality issues
   raw_data = pd.read_csv("raw_hydrological_data.csv", parse_dates=['date'])
   raw_data.set_index('date', inplace=True)
   
   # Check data quality
   print("Data Quality Assessment:")
   print(f"Total records: {len(raw_data)}")
   print(f"Missing values: {raw_data.isnull().sum().sum()}")
   print(f"Duplicate dates: {raw_data.index.duplicated().sum()}")
   
   # Remove duplicates
   clean_data = raw_data[~raw_data.index.duplicated(keep='first')]
   
   # Detect outliers using multiple methods
   outlier_methods = ['iqr', 'zscore', 'isolation_forest']
   outlier_results = {}
   
   for column in ['flow', 'rainfall', 'temperature']:
       if column in clean_data.columns:
           outlier_results[column] = {}
           for method in outlier_methods:
               outliers = detect_outliers(
                   data=clean_data[column],
                   method=method,
                   threshold=3.0 if method == 'zscore' else None
               )
               outlier_results[column][method] = outliers
               print(f"{column} - {method}: {outliers.sum()} outliers detected")
   
   # Visualize outliers
   fig, axes = plt.subplots(len(outlier_results), 1, figsize=(12, 4*len(outlier_results)))
   if len(outlier_results) == 1:
       axes = [axes]
   
   for i, (column, methods) in enumerate(outlier_results.items()):
       ax = axes[i]
       
       # Plot original data
       ax.plot(clean_data.index, clean_data[column], 'b-', alpha=0.7, label='Original')
       
       # Highlight outliers from different methods
       colors = ['red', 'orange', 'purple']
       for j, (method, outliers) in enumerate(methods.items()):
           outlier_data = clean_data[column][outliers]
           ax.scatter(outlier_data.index, outlier_data.values, 
                     c=colors[j], s=20, alpha=0.8, label=f'{method} outliers')
       
       ax.set_ylabel(column.title())
       ax.set_title(f'Outlier Detection: {column.title()}')
       ax.legend()
       ax.grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()
   
   # Fill missing data
   filled_data = clean_data.copy()
   
   for column in clean_data.columns:
       if clean_data[column].isnull().any():
           print(f"\nFilling missing data for {column}:")
           
           # Try different filling methods
           methods = ['linear', 'spline', 'seasonal']
           
           for method in methods:
               try:
                   filled_series = fill_missing_data(
                       data=clean_data[column],
                       method=method,
                       max_gap_hours=24 if method != 'seasonal' else 168
                   )
                   
                   missing_before = clean_data[column].isnull().sum()
                   missing_after = filled_series.isnull().sum()
                   
                   print(f"  {method}: {missing_before} -> {missing_after} missing values")
                   
                   if missing_after < missing_before:
                       filled_data[column] = filled_series
                       break
                       
               except Exception as e:
                   print(f"  {method}: Failed ({str(e)})")
   
   # Validate data consistency
   consistency_report = validate_data_consistency(
       data=filled_data,
       rules={
           'flow_positive': 'flow >= 0',
           'rainfall_positive': 'rainfall >= 0',
           'temp_reasonable': '-50 <= temperature <= 60',
           'flow_rainfall_correlation': 'correlation(flow, rainfall) > 0.1'
       }
   )
   
   print("\nData Consistency Report:")
   for rule, result in consistency_report.items():
       status = "PASS" if result['passed'] else "FAIL"
       print(f"  {rule}: {status} ({result['details']})")
   
   # Plot before and after comparison
   fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
   
   # Before cleaning
   axes[0].plot(raw_data.index, raw_data['flow'], 'r-', alpha=0.7, label='Raw Data')
   axes[0].set_ylabel('Flow (m³/s)')
   axes[0].set_title('Before Data Quality Control')
   axes[0].legend()
   axes[0].grid(True, alpha=0.3)
   
   # After cleaning
   axes[1].plot(filled_data.index, filled_data['flow'], 'g-', alpha=0.7, label='Cleaned Data')
   axes[1].set_ylabel('Flow (m³/s)')
   axes[1].set_xlabel('Date')
   axes[1].set_title('After Data Quality Control')
   axes[1].legend()
   axes[1].grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()
   
   # Save cleaned data
   filled_data.to_csv("cleaned_hydrological_data.csv")
   print("\nCleaned data saved to 'cleaned_hydrological_data.csv'")

Time Series Analysis
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.time_series import (
       resample_data, detect_trends, seasonal_decomposition, 
       calculate_flow_duration_curve
   )
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   from scipy import stats
   
   # Load time series data
   ts_data = pd.read_csv("time_series_data.csv", parse_dates=['date'])
   ts_data.set_index('date', inplace=True)
   
   # Resample data to different frequencies
   resampling_frequencies = {
       'Daily': 'D',
       'Weekly': 'W',
       'Monthly': 'M',
       'Quarterly': 'Q',
       'Annual': 'A'
   }
   
   resampled_data = {}
   for name, freq in resampling_frequencies.items():
       resampled = resample_data(
           data=ts_data['flow'],
           target_frequency=freq,
           aggregation_method='mean'
       )
       resampled_data[name] = resampled
       print(f"{name} resampling: {len(ts_data)} -> {len(resampled)} points")
   
   # Plot different time scales
   fig, axes = plt.subplots(2, 2, figsize=(15, 10))
   axes = axes.flatten()
   
   plot_data = [('Daily', ts_data['flow']), ('Weekly', resampled_data['Weekly']),
                ('Monthly', resampled_data['Monthly']), ('Annual', resampled_data['Annual'])]
   
   for i, (name, data) in enumerate(plot_data):
       axes[i].plot(data.index, data.values, 'b-', alpha=0.7)
       axes[i].set_title(f'{name} Flow Data')
       axes[i].set_ylabel('Flow (m³/s)')
       axes[i].grid(True, alpha=0.3)
       
       if i >= 2:  # Bottom row
           axes[i].set_xlabel('Date')
   
   plt.tight_layout()
   plt.show()
   
   # Trend analysis
   trend_results = detect_trends(
       data=resampled_data['Monthly'],
       methods=['mann_kendall', 'linear_regression', 'theil_sen']
   )
   
   print("\nTrend Analysis Results:")
   for method, result in trend_results.items():
       print(f"{method}:")
       print(f"  Trend: {result['trend']}")
       print(f"  p-value: {result['p_value']:.4f}")
       print(f"  Slope: {result['slope']:.6f} m³/s per month")
   
   # Seasonal decomposition
   decomposition = seasonal_decomposition(
       data=resampled_data['Monthly'],
       model='additive',
       period=12  # Monthly data, annual cycle
   )
   
   # Plot decomposition
   fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
   
   components = ['observed', 'trend', 'seasonal', 'residual']
   titles = ['Original', 'Trend', 'Seasonal', 'Residual']
   
   for i, (comp, title) in enumerate(zip(components, titles)):
       data = getattr(decomposition, comp)
       axes[i].plot(data.index, data.values, 'b-', alpha=0.7)
       axes[i].set_ylabel(title)
       axes[i].grid(True, alpha=0.3)
   
   axes[-1].set_xlabel('Date')
   plt.suptitle('Seasonal Decomposition of Monthly Flow')
   plt.tight_layout()
   plt.show()
   
   # Flow duration curve
   fdc_data = calculate_flow_duration_curve(ts_data['flow'])
   
   plt.figure(figsize=(10, 6))
   plt.semilogy(fdc_data['exceedance_probability'] * 100, fdc_data['flow'], 'b-', linewidth=2)
   plt.xlabel('Exceedance Probability (%)')
   plt.ylabel('Flow (m³/s)')
   plt.title('Flow Duration Curve')
   plt.grid(True, alpha=0.3)
   
   # Add percentile markers
   percentiles = [5, 10, 25, 50, 75, 90, 95]
   for p in percentiles:
       flow_value = np.percentile(ts_data['flow'].dropna(), 100-p)
       plt.axhline(y=flow_value, color='r', linestyle='--', alpha=0.5)
       plt.axvline(x=p, color='r', linestyle='--', alpha=0.5)
       plt.text(p+1, flow_value, f'Q{p}', fontsize=8, color='red')
   
   plt.show()
   
   # Calculate flow statistics
   flow_stats = {
       'Q5': np.percentile(ts_data['flow'].dropna(), 95),
       'Q10': np.percentile(ts_data['flow'].dropna(), 90),
       'Q25': np.percentile(ts_data['flow'].dropna(), 75),
       'Q50': np.percentile(ts_data['flow'].dropna(), 50),
       'Q75': np.percentile(ts_data['flow'].dropna(), 25),
       'Q90': np.percentile(ts_data['flow'].dropna(), 10),
       'Q95': np.percentile(ts_data['flow'].dropna(), 5),
       'Mean': ts_data['flow'].mean(),
       'Std': ts_data['flow'].std(),
       'CV': ts_data['flow'].std() / ts_data['flow'].mean()
   }
   
   print("\nFlow Statistics:")
   for stat, value in flow_stats.items():
       print(f"{stat}: {value:.2f} m³/s" if stat != 'CV' else f"{stat}: {value:.3f}")

Advanced Preprocessing Techniques
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.advanced import (
       wavelet_denoising, empirical_mode_decomposition,
       change_point_detection, data_fusion
   )
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   
   # Load noisy time series data
   noisy_data = pd.read_csv("noisy_streamflow.csv", parse_dates=['date'])
   noisy_data.set_index('date', inplace=True)
   
   # Wavelet denoising
   denoised_flow = wavelet_denoising(
       data=noisy_data['flow'],
       wavelet='db4',
       levels=6,
       threshold_method='soft',
       threshold_mode='sure'
   )
   
   # Plot original vs denoised
   plt.figure(figsize=(12, 6))
   plt.plot(noisy_data.index, noisy_data['flow'], 'b-', alpha=0.5, label='Original')
   plt.plot(denoised_flow.index, denoised_flow.values, 'r-', linewidth=2, label='Denoised')
   plt.xlabel('Date')
   plt.ylabel('Flow (m³/s)')
   plt.title('Wavelet Denoising of Streamflow Data')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()
   
   # Empirical Mode Decomposition (EMD)
   emd_components = empirical_mode_decomposition(
       data=noisy_data['flow'],
       max_imfs=8
   )
   
   # Plot EMD components
   n_components = len(emd_components)
   fig, axes = plt.subplots(n_components, 1, figsize=(12, 2*n_components), sharex=True)
   
   for i, (name, component) in enumerate(emd_components.items()):
       axes[i].plot(component.index, component.values, 'b-', alpha=0.7)
       axes[i].set_ylabel(name)
       axes[i].grid(True, alpha=0.3)
   
   axes[-1].set_xlabel('Date')
   plt.suptitle('Empirical Mode Decomposition')
   plt.tight_layout()
   plt.show()
   
   # Change point detection
   change_points = change_point_detection(
       data=noisy_data['flow'],
       method='pelt',
       penalty=10,
       min_size=30
   )
   
   print(f"\nDetected {len(change_points)} change points:")
   for i, cp in enumerate(change_points):
       print(f"  Change point {i+1}: {cp}")
   
   # Plot change points
   plt.figure(figsize=(12, 6))
   plt.plot(noisy_data.index, noisy_data['flow'], 'b-', alpha=0.7, label='Flow')
   
   for cp in change_points:
       plt.axvline(x=cp, color='r', linestyle='--', alpha=0.8)
   
   plt.xlabel('Date')
   plt.ylabel('Flow (m³/s)')
   plt.title('Change Point Detection in Streamflow')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()
   
   # Data fusion example (combining multiple data sources)
   # Load additional data sources
   satellite_data = pd.read_csv("satellite_flow_estimates.csv", parse_dates=['date'])
   satellite_data.set_index('date', inplace=True)
   
   model_data = pd.read_csv("model_flow_predictions.csv", parse_dates=['date'])
   model_data.set_index('date', inplace=True)
   
   # Fuse multiple data sources
   fused_data = data_fusion(
       primary_data=noisy_data['flow'],
       secondary_data={
           'satellite': satellite_data['flow_estimate'],
           'model': model_data['flow_prediction']
       },
       fusion_method='weighted_average',
       weights={'primary': 0.6, 'satellite': 0.25, 'model': 0.15},
       quality_control=True
   )
   
   # Compare data sources
   plt.figure(figsize=(12, 8))
   
   plt.subplot(2, 1, 1)
   plt.plot(noisy_data.index, noisy_data['flow'], 'b-', alpha=0.7, label='Gauge Data')
   plt.plot(satellite_data.index, satellite_data['flow_estimate'], 'g-', alpha=0.7, label='Satellite')
   plt.plot(model_data.index, model_data['flow_prediction'], 'orange', alpha=0.7, label='Model')
   plt.ylabel('Flow (m³/s)')
   plt.title('Multiple Data Sources')
   plt.legend()
   plt.grid(True, alpha=0.3)
   
   plt.subplot(2, 1, 2)
   plt.plot(fused_data.index, fused_data.values, 'r-', linewidth=2, label='Fused Data')
   plt.plot(noisy_data.index, noisy_data['flow'], 'b-', alpha=0.5, label='Original Gauge')
   plt.xlabel('Date')
   plt.ylabel('Flow (m³/s)')
   plt.title('Data Fusion Result')
   plt.legend()
   plt.grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()

Statistical Analysis
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.statistics import (
       frequency_analysis, correlation_analysis, 
       extreme_value_analysis, autocorrelation_analysis
   )
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   from scipy import stats
   
   # Load long-term flow data for statistical analysis
   long_term_data = pd.read_csv("long_term_flow_data.csv", parse_dates=['date'])
   long_term_data.set_index('date', inplace=True)
   
   # Frequency analysis
   annual_maxima = long_term_data['flow'].resample('A').max()
   
   frequency_results = frequency_analysis(
       data=annual_maxima,
       distributions=['gumbel', 'gev', 'lognormal', 'pearson3'],
       return_periods=[2, 5, 10, 25, 50, 100, 200]
   )
   
   print("Frequency Analysis Results:")
   for dist_name, results in frequency_results.items():
       print(f"\n{dist_name.upper()} Distribution:")
       print(f"  Parameters: {results['parameters']}")
       print(f"  Goodness of fit (KS test): p = {results['ks_pvalue']:.4f}")
       
       print("  Return period estimates:")
       for rp, estimate in results['return_period_estimates'].items():
           print(f"    {rp}-year: {estimate:.1f} m³/s")
   
   # Plot frequency analysis
   fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
   
   # Probability plot
   for dist_name, results in frequency_results.items():
       rp_values = list(results['return_period_estimates'].keys())
       flow_values = list(results['return_period_estimates'].values())
       ax1.semilogx(rp_values, flow_values, 'o-', label=dist_name, markersize=4)
   
   ax1.set_xlabel('Return Period (years)')
   ax1.set_ylabel('Flow (m³/s)')
   ax1.set_title('Flood Frequency Analysis')
   ax1.legend()
   ax1.grid(True, alpha=0.3)
   
   # Histogram with fitted distributions
   ax2.hist(annual_maxima.values, bins=20, density=True, alpha=0.7, color='lightblue')
   
   x_range = np.linspace(annual_maxima.min(), annual_maxima.max(), 100)
   for dist_name, results in frequency_results.items():
       if dist_name == 'gumbel':
           fitted_dist = stats.gumbel_r(*results['parameters'])
           ax2.plot(x_range, fitted_dist.pdf(x_range), '-', label=f'{dist_name} fit', linewidth=2)
   
   ax2.set_xlabel('Annual Maximum Flow (m³/s)')
   ax2.set_ylabel('Probability Density')
   ax2.set_title('Distribution Fitting')
   ax2.legend()
   ax2.grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()
   
   # Correlation analysis
   # Load additional variables
   climate_data = pd.read_csv("climate_data.csv", parse_dates=['date'])
   climate_data.set_index('date', inplace=True)
   
   # Combine datasets
   combined_data = pd.concat([long_term_data, climate_data], axis=1).dropna()
   
   correlation_results = correlation_analysis(
       data=combined_data,
       target_variable='flow',
       methods=['pearson', 'spearman', 'kendall'],
       lag_analysis=True,
       max_lag=30
   )
   
   print("\nCorrelation Analysis:")
   for method, results in correlation_results.items():
       if method != 'lag_analysis':
           print(f"\n{method.title()} Correlations with Flow:")
           for var, corr in results.items():
               if var != 'flow':
                   print(f"  {var}: {corr['correlation']:.3f} (p = {corr['p_value']:.4f})")
   
   # Plot correlation matrix
   correlation_matrix = combined_data.corr()
   
   plt.figure(figsize=(10, 8))
   im = plt.imshow(correlation_matrix.values, cmap='RdBu_r', vmin=-1, vmax=1)
   plt.colorbar(im, label='Correlation Coefficient')
   
   # Add labels
   variables = correlation_matrix.columns
   plt.xticks(range(len(variables)), variables, rotation=45, ha='right')
   plt.yticks(range(len(variables)), variables)
   
   # Add correlation values
   for i in range(len(variables)):
       for j in range(len(variables)):
           plt.text(j, i, f'{correlation_matrix.iloc[i, j]:.2f}', 
                   ha='center', va='center', fontsize=8)
   
   plt.title('Correlation Matrix')
   plt.tight_layout()
   plt.show()
   
   # Lag correlation analysis
   if 'lag_analysis' in correlation_results:
       lag_results = correlation_results['lag_analysis']
       
       fig, axes = plt.subplots(2, 2, figsize=(12, 8))
       axes = axes.flatten()
       
       variables_to_plot = ['precipitation', 'temperature', 'humidity', 'pressure']
       
       for i, var in enumerate(variables_to_plot[:4]):
           if var in lag_results:
               lags = lag_results[var]['lags']
               correlations = lag_results[var]['correlations']
               
               axes[i].plot(lags, correlations, 'b-o', markersize=3)
               axes[i].axhline(y=0, color='k', linestyle='--', alpha=0.5)
               axes[i].set_xlabel('Lag (days)')
               axes[i].set_ylabel('Correlation')
               axes[i].set_title(f'Lag Correlation: Flow vs {var.title()}')
               axes[i].grid(True, alpha=0.3)
               
               # Mark maximum correlation
               max_idx = np.argmax(np.abs(correlations))
               max_lag = lags[max_idx]
               max_corr = correlations[max_idx]
               axes[i].plot(max_lag, max_corr, 'ro', markersize=6)
               axes[i].text(max_lag, max_corr + 0.05, f'Max: {max_corr:.3f}\nat lag {max_lag}', 
                           ha='center', fontsize=8)
       
       plt.tight_layout()
       plt.show()
   
   # Autocorrelation analysis
   autocorr_results = autocorrelation_analysis(
       data=long_term_data['flow'],
       max_lag=365,  # One year
       confidence_level=0.95
   )
   
   plt.figure(figsize=(12, 6))
   
   plt.subplot(1, 2, 1)
   lags = autocorr_results['lags']
   acf = autocorr_results['autocorrelation']
   confidence_bounds = autocorr_results['confidence_bounds']
   
   plt.plot(lags, acf, 'b-', linewidth=1)
   plt.fill_between(lags, -confidence_bounds, confidence_bounds, 
                    alpha=0.3, color='gray', label='95% Confidence')
   plt.axhline(y=0, color='k', linestyle='-', alpha=0.5)
   plt.xlabel('Lag (days)')
   plt.ylabel('Autocorrelation')
   plt.title('Autocorrelation Function')
   plt.legend()
   plt.grid(True, alpha=0.3)
   
   plt.subplot(1, 2, 2)
   pacf = autocorr_results['partial_autocorrelation']
   plt.plot(lags, pacf, 'r-', linewidth=1)
   plt.fill_between(lags, -confidence_bounds, confidence_bounds, 
                    alpha=0.3, color='gray', label='95% Confidence')
   plt.axhline(y=0, color='k', linestyle='-', alpha=0.5)
   plt.xlabel('Lag (days)')
   plt.ylabel('Partial Autocorrelation')
   plt.title('Partial Autocorrelation Function')
   plt.legend()
   plt.grid(True, alpha=0.3)
   
   plt.tight_layout()
   plt.show()
   
   # Identify significant lags
   significant_lags = lags[np.abs(acf) > confidence_bounds]
   print(f"\nSignificant autocorrelation lags: {significant_lags[:10]}...")  # Show first 10

Configuration and Parameters
----------------------------

Baseflow Separation Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Lyne-Hollick Filter:**

.. code-block:: python

   lyne_hollick_params = {
       'alpha': 0.925,        # Filter parameter (0.9-0.95 typical)
       'passes': 3,           # Number of filter passes (1-3)
       'n_reflect': 30        # Reflection points for boundary conditions
   }

**Other Baseflow Methods:**

.. code-block:: python

   # UKIH method
   ukih_params = {
       'block_length': 5,     # Block length in days
       'f': 0.9              # Recession constant
   }
   
   # Eckhardt method
   eckhardt_params = {
       'alpha': 0.98,        # Recession constant
       'BFI_max': 0.8        # Maximum baseflow index
   }

Data Quality Parameters
~~~~~~~~~~~~~~~~~~~~~~~

**Outlier Detection:**

.. code-block:: python

   outlier_params = {
       'iqr_multiplier': 1.5,     # IQR method multiplier
       'zscore_threshold': 3.0,    # Z-score threshold
       'isolation_contamination': 0.1  # Isolation forest contamination
   }

**Gap Filling:**

.. code-block:: python

   gap_filling_params = {
       'max_gap_hours': 24,       # Maximum gap to fill (hours)
       'min_data_points': 10,     # Minimum points for interpolation
       'spline_order': 3,         # Spline interpolation order
       'seasonal_period': 365     # Seasonal decomposition period
   }

Performance Optimization
------------------------

Memory Management
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Optimize memory usage for large datasets
   preprocessing_config = {
       'chunk_size': 10000,       # Process data in chunks
       'use_dask': True,          # Use Dask for parallel processing
       'memory_limit': '4GB',     # Memory limit per worker
       'cache_intermediate': False # Don't cache intermediate results
   }

Parallel Processing
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.parallel import ParallelProcessor
   
   # Create parallel processor
   processor = ParallelProcessor(
       n_workers=4,
       backend='multiprocessing'
   )
   
   # Process multiple time series in parallel
   results = processor.map(
       function=lyne_hollick_filter,
       data_list=multiple_flow_series,
       alpha=0.925,
       passes=3
   )

Error Handling and Validation
-----------------------------

Common Issues
~~~~~~~~~~~~~

**Data Issues:**

- Missing timestamps
- Irregular time intervals
- Negative flow values
- Unrealistic data ranges
- Duplicate records

**Processing Issues:**

- Insufficient data for analysis
- Numerical instability
- Memory limitations
- Convergence problems

Validation Framework
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from preprocessing.validation import DataValidator
   
   # Create validator
   validator = DataValidator()
   
   # Define validation rules
   validation_rules = {
       'temporal_consistency': {
           'regular_intervals': True,
           'no_gaps_larger_than': '1D',
           'chronological_order': True
       },
       'value_constraints': {
           'flow_min': 0.0,
           'flow_max': 10000.0,
           'rainfall_min': 0.0,
           'temperature_range': (-50, 60)
       },
       'statistical_checks': {
           'outlier_threshold': 3.0,
           'missing_data_max': 0.1,
           'variance_min': 0.001
       }
   }
   
   # Validate data
   validation_report = validator.validate(
       data=raw_data,
       rules=validation_rules
   )
   
   # Print validation results
   for check, result in validation_report.items():
       status = "PASS" if result['passed'] else "FAIL"
       print(f"{check}: {status}")
       if not result['passed']:
           print(f"  Issues: {result['issues']}")

Output and Reporting
--------------------

Data Export
~~~~~~~~~~~

.. code-block:: python

   from preprocessing.export import DataExporter
   
   # Create exporter
   exporter = DataExporter()
   
   # Export to various formats
   exporter.to_csv(processed_data, "processed_data.csv")
   exporter.to_netcdf(processed_data, "processed_data.nc")
   exporter.to_hdf5(processed_data, "processed_data.h5")
   
   # Export with metadata
   exporter.to_csv_with_metadata(
       data=processed_data,
       filename="processed_data.csv",
       metadata={
           'processing_date': pd.Timestamp.now(),
           'methods_used': ['lyne_hollick', 'outlier_removal'],
           'data_source': 'gauge_station_001',
           'quality_flags': validation_report
       }
   )

Reporting
~~~~~~~~~

.. code-block:: python

   from preprocessing.reporting import ProcessingReport
   
   # Generate processing report
   report = ProcessingReport()
   
   report.add_section("Data Summary", {
       'total_records': len(processed_data),
       'date_range': f"{processed_data.index.min()} to {processed_data.index.max()}",
       'missing_data': processed_data.isnull().sum().to_dict(),
       'data_quality_score': validation_report['overall_score']
   })
   
   report.add_section("Processing Steps", {
       'outlier_removal': f"{outlier_count} outliers removed",
       'gap_filling': f"{gaps_filled} gaps filled",
       'baseflow_separation': f"BFI = {baseflow_index:.3f}",
       'data_validation': "All checks passed"
   })
   
   report.add_plots([
       ('time_series', time_series_plot),
       ('baseflow_separation', baseflow_plot),
       ('quality_control', quality_plot)
   ])
   
   # Export report
   report.to_html("preprocessing_report.html")
   report.to_pdf("preprocessing_report.pdf")