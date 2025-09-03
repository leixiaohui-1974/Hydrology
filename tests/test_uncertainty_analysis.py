import unittest
import sys
import os
import numpy as np
import warnings

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hydro_model.uncertainty.monte_carlo import MonteCarloAnalyzer
from hydro_model.uncertainty.sensitivity_analysis import SensitivityAnalyzer
from hydro_model.uncertainty.bayesian_analysis import BayesianUncertaintyAnalyzer

# --- Test Models ---

def ishigami_function(params):
    """
    The Ishigami function is a standard test function for sensitivity analysis.
    Inputs X1, X2, X3 are sampled from U(-pi, pi).
    """
    a = 7.0
    b = 0.1
    x1 = params['x1']
    x2 = params['x2']
    x3 = params['x3']

    term1 = np.sin(x1)
    term2 = a * np.sin(x2)**2
    term3 = b * x3**4 * np.sin(x1)

    return term1 + term2 + term3

def linear_model(params):
    """A simple linear model for testing Bayesian inference."""
    m = params.get('m', 1.0) # Default to 1 if not in params
    c = params.get('c', 0.0) # Default to 0 if not in params
    x = params['x']
    return m * x + c

def simple_model_for_mc(params):
    """A simple top-level model for Monte Carlo testing."""
    return params['param1'] * params['param2']

class BayesianLinearModel:
    """
    A pickleable class to wrap the linear model for Bayesian testing,
    as local functions cannot be pickled by multiprocessing.
    """
    def __init__(self, x_data):
        self.x_data = x_data

    def __call__(self, params, times=None):
        params_with_x = params.copy()
        params_with_x['x'] = self.x_data
        return linear_model(params_with_x)


class TestUncertaintyAnalysis(unittest.TestCase):

    def test_monte_carlo_analyzer_run(self):
        """
        Tests that the MonteCarloAnalyzer can be initialized and run without errors.
        """
        print("\nRunning test_monte_carlo_analyzer_run...")
        analyzer = MonteCarloAnalyzer(n_samples=100, random_seed=42, n_workers=2)

        analyzer.add_parameter_distribution('param1', 'normal', mean=10, std=2)
        analyzer.add_parameter_distribution('param2', 'uniform', low=0, high=1)

        try:
            results = analyzer.run_monte_carlo(simple_model_for_mc)
            self.assertIsNotNone(results)
            self.assertEqual(len(results), 100)
            # Check that there are no errors in the output
            self.assertTrue('error' not in results.columns or results['error'].isna().all())
            print("MonteCarloAnalyzer run test passed.")
        except Exception as e:
            self.fail(f"MonteCarloAnalyzer run failed with an exception: {e}")

    def test_sobol_analysis_ishigami(self):
        """
        Tests the Sobol sensitivity analysis against the Ishigami function,
        for which the analytical sensitivity indices are known.
        """
        print("\nRunning test_sobol_analysis_ishigami...")
        # For the Ishigami function with a=7, b=0.1, the analytical first-order
        # indices for X1, X2, X3 are known.
        # S1(X1) approx 0.3139
        # S1(X2) approx 0.4424
        # S1(X3) = 0.0
        # Total variance is approx 13.8

        analyzer = SensitivityAnalyzer(n_samples=2000, n_workers=2)

        # Parameters are sampled from U(-pi, pi)
        pi = np.pi
        analyzer.add_parameter('x1', (-pi, pi), 'uniform')
        analyzer.add_parameter('x2', (-pi, pi), 'uniform')
        analyzer.add_parameter('x3', (-pi, pi), 'uniform')

        results = analyzer.sobol_analysis(ishigami_function)

        # The analytical values
        s1_analytical = {'x1': 0.3139, 'x2': 0.4424, 'x3': 0.0}

        print("Calculated Sobol Indices:", results['first_order'])

        # Check if the calculated indices are close to the analytical ones
        for param, analytical_value in s1_analytical.items():
            calculated_value = results['first_order'][param]
            self.assertAlmostEqual(
                calculated_value,
                analytical_value,
                places=1, # Sobol indices converge slowly, so tolerance must be loose
                msg=f"Sobol first-order index for {param} is incorrect."
            )

        print("Sobol analysis test passed.")

    def test_bayesian_analyzer_linear_model(self):
        """
        Tests if the BayesianUncertaintyAnalyzer can recover the parameters
        of a simple linear model from synthetic data.
        """
        print("\nRunning test_bayesian_analyzer_linear_model...")

        # 1. Generate synthetic data with known parameters
        true_m = 2.5
        true_c = 1.0
        true_sigma = 0.5
        x_data = np.linspace(0, 10, 20)
        y_data = true_m * x_data + true_c + np.random.normal(0, true_sigma, len(x_data))

        # 2. Set up the analyzer
        # Suppress the warning about the simplified error model if it appears
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)

            analyzer = BayesianUncertaintyAnalyzer(n_walkers=32, n_steps=2000, n_burn=500, n_workers=2)

            # Define priors around the true values
            analyzer.add_parameter('m', 'normal', mean=2, std=1)
            analyzer.add_parameter('c', 'normal', mean=1, std=1)
            analyzer.add_parameter('sigma', 'uniform', low=0.01, high=2.0)

            # Set data and model
            analyzer.set_observations(y_data)

            # Use the pickleable class wrapper for the model
            model_for_bayes = BayesianLinearModel(x_data)
            analyzer.set_model_function(model_for_bayes)

            # 3. Run MCMC
            results = analyzer.run_mcmc()

            # 4. Check if the posterior means are close to the true values
            posterior_stats = results['posterior_stats']
            print("Posterior means:", {k: v['mean'] for k, v in posterior_stats.items()})

            self.assertAlmostEqual(posterior_stats['m']['mean'], true_m, delta=0.5)
            self.assertAlmostEqual(posterior_stats['c']['mean'], true_c, delta=0.5)
            self.assertAlmostEqual(posterior_stats['sigma']['mean'], true_sigma, delta=0.5)

            print("Bayesian analysis test passed.")


if __name__ == '__main__':
    unittest.main()
