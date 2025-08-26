import unittest
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path

# Adjust path to import from the root of the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hydro_model.ml_integration.feature_engineering import TimeSeriesFeatureEngineer
from hydro_model.ml_integration.traditional_ml import RandomForestRegressor
from hydro_model.ml_integration.base_ml_model import MLModelWrapper

class TestMLIntegration(unittest.TestCase):

    def setUp(self):
        """Set up a sample time-series DataFrame for testing."""
        self.dates = pd.to_datetime(pd.date_range(start='2023-01-01', periods=20, freq='H'))
        self.data = {
            'rainfall': np.arange(20, dtype=float),
            'temperature': np.linspace(10, 20, 20)
        }
        self.df = pd.DataFrame(self.data, index=self.dates)

    def test_time_series_feature_engineer(self):
        """
        Tests that the TimeSeriesFeatureEngineer correctly creates lag and rolling features.
        """
        print("\nRunning test_time_series_feature_engineer...")

        lags = [1, 2]
        windows = [3, 6]

        engineer = TimeSeriesFeatureEngineer(lag_features=lags, rolling_window_sizes=windows)

        features_df = engineer.fit_transform(self.df)

        # Expected number of features:
        # 2 original + 2 (lags) * 2 (cols) + 3 (stats) * 2 (windows) * 2 (cols) = 2 + 4 + 12 = 18
        self.assertEqual(features_df.shape[1], 18)

        # Check if expected columns are present
        self.assertIn('rainfall_lag_1', features_df.columns)
        self.assertIn('temperature_rolling_mean_3', features_df.columns)

        # Check that the first value of lag 1 is correct
        # The largest rolling window is 6, so the first 5 rows will be dropped.
        # The first row of `features_df` corresponds to index 5 of the original `self.df`.
        # The `rainfall_lag_1` feature at this row should be the rainfall value
        # from the previous time step (index 4).
        self.assertEqual(features_df['rainfall_lag_1'].iloc[0], self.df['rainfall'].iloc[4])

        print("TimeSeriesFeatureEngineer test passed.")

    def test_model_wrapper_save_load(self):
        """
        Tests the save and load functionality of the MLModelWrapper via a concrete implementation.
        """
        print("\nRunning test_model_wrapper_save_load...")

        # Create some simple data
        X = np.random.rand(20, 5)
        y = np.random.rand(20)

        # Instantiate and fit the model
        rf_model = RandomForestRegressor(n_estimators=10, random_state=42)
        rf_model.fit(X, y)

        # Save the model
        model_path = Path("./test_model.joblib")
        rf_model.save(model_path)

        # Check if the file was created
        self.assertTrue(model_path.exists())

        # Load the model into a new instance
        loaded_model = RandomForestRegressor()
        loaded_model.load(model_path)

        # Check if the loaded model can predict and gives the same result
        prediction_original = rf_model.predict(X)
        prediction_loaded = loaded_model.predict(X)

        np.testing.assert_array_almost_equal(prediction_original, prediction_loaded)

        # Clean up the created file
        os.remove(model_path)
        print("Model save/load test passed.")


if __name__ == '__main__':
    unittest.main()
