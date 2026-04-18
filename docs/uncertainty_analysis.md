# Uncertainty and Sensitivity Analysis

The Hydro-Suite includes a powerful module for Uncertainty Analysis (UA) and Sensitivity Analysis (SA) located in `hydro_model.uncertainty`. These tools are essential for understanding model behavior, quantifying prediction confidence, and identifying the most influential parameters.

This module was recently stabilized and enhanced, moving from a prototype to a more robust implementation.

## Core Components

The module provides three main analyzers:

1.  **`MonteCarloAnalyzer`**: For propagating input parameter uncertainty through a model to understand the uncertainty in the output.
2.  **`SensitivityAnalyzer`**: For identifying which input parameters have the most significant impact on the model's output. It includes multiple methods for global sensitivity analysis.
3.  **`BayesianUncertaintyAnalyzer`**: For performing Bayesian inference to estimate model parameters and their uncertainty based on observed data.

---

## 1. Monte Carlo Analysis

The `MonteCarloAnalyzer` allows you to define probability distributions for your model parameters, draws a large number of samples from these distributions, runs your model for each sample, and analyzes the resulting distribution of model outputs.

### Quick Example

```python
from hydro_model.uncertainty.monte_carlo import MonteCarloAnalyzer

# 1. Initialize the analyzer
analyzer = MonteCarloAnalyzer(n_samples=5000, random_seed=42)

# 2. Define parameter distributions
analyzer.add_parameter_distribution('param1', 'normal', mean=50, std=10)
analyzer.add_parameter_distribution('param2', 'uniform', low=0.1, high=0.5)

# 3. Define your model function
def my_model(params):
    return params['param1'] ** params['param2']

# 4. Run the analysis
results = analyzer.run_monte_carlo(my_model)

# 5. Get results
print(analyzer.get_summary_report())
analyzer.plot_output_distributions()
```

---

## 2. Sensitivity Analysis

The `SensitivityAnalyzer` helps you rank your model parameters by importance. This is crucial for model calibration and simplification. The implementation includes the **Sobol** method, a robust variance-based global sensitivity analysis technique.

### Sobol Analysis Example

The Sobol method decomposes the variance of the model output into fractions that can be attributed to each input parameter (first-order indices) and their interactions (total-order indices).

```python
from hydro_model.uncertainty.sensitivity_analysis import SensitivityAnalyzer
import numpy as np

# 1. Initialize the analyzer
analyzer = SensitivityAnalyzer(n_samples=1000)

# 2. Define parameter bounds
pi = np.pi
analyzer.add_parameter('x1', (-pi, pi), 'uniform')
analyzer.add_parameter('x2', (-pi, pi), 'uniform')
analyzer.add_parameter('x3', (-pi, pi), 'uniform')

# 3. Define the model (e.g., the Ishigami function)
def ishigami_function(params):
    a = 7.0
    b = 0.1
    x1, x2, x3 = params['x1'], params['x2'], params['x3']
    return np.sin(x1) + a * np.sin(x2)**2 + b * x3**4 * np.sin(x1)

# 4. Run the analysis
results = analyzer.sobol_analysis(ishigami_function)

# 5. Get results
print(analyzer.get_summary_report())
analyzer.plot_sensitivity_results(method='sobol')
```

---

## 3. Bayesian Uncertainty Analysis

The `BayesianUncertaintyAnalyzer` uses Markov Chain Monte Carlo (MCMC) to estimate the posterior probability distribution of your model parameters, given a set of observations. This is the most thorough way to perform parameter estimation and uncertainty quantification.

The implementation uses the `emcee` library.

### Example

```python
from hydro_model.uncertainty.bayesian_analysis import BayesianUncertaintyAnalyzer
import numpy as np

# 1. Define a model and generate some synthetic data
true_params = {'m': 2.5, 'c': 1.0, 'sigma': 0.5}
x_data = np.linspace(0, 10, 20)
y_data = (true_params['m'] * x_data + true_params['c'] +
          np.random.normal(0, true_params['sigma'], len(x_data)))

def linear_model(params, times=None):
    # 'times' is unused here but required by the analyzer's interface
    return params['m'] * x_data + params['c']

# 2. Initialize the analyzer
analyzer = BayesianUncertaintyAnalyzer(n_walkers=32, n_steps=2000, n_burn=500)

# 3. Define priors for the parameters, including the error term 'sigma'
analyzer.add_parameter('m', 'normal', mean=2, std=1)
analyzer.add_parameter('c', 'normal', mean=1, std=1)
analyzer.add_parameter('sigma', 'uniform', low=0.01, high=2.0)

# 4. Set the data and model
analyzer.set_observations(y_data)
analyzer.set_model_function(linear_model)

# 5. Run the MCMC analysis
results = analyzer.run_mcmc()

# 6. Get results
print(analyzer.get_summary_report())
analyzer.plot_posterior_distributions()
```
