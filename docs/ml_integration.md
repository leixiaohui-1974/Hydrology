# Machine Learning Integration

The Hydro-Suite includes a module for Machine Learning (ML) integration located in `hydro_model.ml_integration`. This framework is designed to allow seamless combination of physics-based hydrological models with data-driven ML models.

## Framework Design

The framework is built on two key concepts:

1.  **Feature Engineering**: The process of creating predictive features from raw time-series data.
2.  **Model Wrapping**: A consistent interface for training, predicting with, and managing various ML models.

### `TimeSeriesFeatureEngineer`

Located in `feature_engineering.py`, this class is designed specifically for hydrological time-series data. Given a pandas DataFrame with a DatetimeIndex, it can automatically generate:
-   **Lag Features**: The value of a variable at previous time steps (e.g., rainfall 1 hour ago).
-   **Rolling Window Features**: Statistics (e.g., mean, sum, standard deviation) calculated over a moving time window.

### `MLModelWrapper`

This is an abstract base class defined in `base_ml_model.py`. It provides a standard API for all machine learning models, ensuring they can be used interchangeably within the framework. Key methods include:
-   `.fit(X, y)`
-   `.predict(X)`
-   `.save(filepath)`
-   `.load(filepath)`

The `traditional_ml.py` module contains several concrete implementations of this wrapper for popular `scikit-learn` models, such as `RandomForestRegressor`.

## Example Workflow: Rainfall-Runoff Prediction

Here is a complete example of how to use the framework to train a model that predicts runoff based on historical rainfall data.

### 1. Load Data

First, load your time-series data into a pandas DataFrame. The index should be a `DatetimeIndex`.

```python
import pandas as pd

# This is a sample CSV file provided in the example directory
data_path = 'examples/ml_integration_example/sample_hydro_data.csv'
df = pd.read_csv(data_path, parse_dates=['timestamp'], index_col='timestamp')

# df should have columns like 'rainfall_mm' and 'runoff_cfs'
```

### 2. Engineer Features

Use the `TimeSeriesFeatureEngineer` to create predictive features from the rainfall data. The target variable is `runoff_cfs`.

```python
from hydro_model.ml_integration.feature_engineering import TimeSeriesFeatureEngineer

# We will use only rainfall to predict runoff
rainfall_df = df[['rainfall_mm']]

# Initialize the engineer with desired lags and windows
feature_engineer = TimeSeriesFeatureEngineer(
    lag_features=[1, 2, 3, 6],          # 1, 2, 3, 6-hour lags
    rolling_window_sizes=[3, 6, 12]  # 3, 6, 12-hour rolling stats
)

# Create the feature set
features_df = feature_engineer.fit_transform(rainfall_df)

# Align the target variable (runoff) with the new features
target = df['runoff_cfs'].loc[features_df.index]
```

### 3. Train the Model

Now, train a machine learning model using the generated features. Here, we use the wrapped `RandomForestRegressor`.

```python
from hydro_model.ml_integration.traditional_ml import RandomForestRegressor
from sklearn.model_selection import train_test_split

# Prepare data for scikit-learn
X = features_df.values
y = target.values

# Split into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Initialize and train the model
rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
rf_model.fit(X_train, y_train)
```

### 4. Evaluate, Save, and Load

Finally, evaluate the model and demonstrate the save/load functionality.

```python
from sklearn.metrics import mean_squared_error

# Evaluate
predictions = rf_model.predict(X_test)
mse = mean_squared_error(y_test, predictions)
print(f"Model MSE: {mse:.4f}")

# Save the model
model_path = './trained_runoff_model.joblib'
rf_model.save(model_path)

# Load the model into a new instance
loaded_model = RandomForestRegressor()
loaded_model.load(model_path)

# Verify that the loaded model works
new_predictions = loaded_model.predict(X_test)
assert np.allclose(predictions, new_predictions)
```
