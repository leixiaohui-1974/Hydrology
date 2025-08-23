# Deep Learning Models for Flow Prediction

This framework now includes support for using deep learning models for hydrological forecasting. Two types of models are provided: a Long Short-Term Memory (LSTM) model and a Graph Neural Network (GNN) model. These models can be used to predict flow at a specific station based on rainfall and other upstream inputs.

## Overview

### LSTM Model

The `LSTMModel` is a time-series forecasting model that uses a sequence of past data (e.g., rainfall over the last 10 days) to predict the flow at the next time step. It's well-suited for single-point predictions where the temporal dependencies are important.

### GNN Model

The `GNNModel` treats the watershed as a graph of interconnected catchments. It uses a Graph Convolutional Network (GCN) to learn the spatial relationships between the catchments. This model is more powerful when you want to model the interactions between different parts of the watershed.

## Components

### `LSTMModel`

This component wraps a pre-trained PyTorch LSTM model.

-   **`type`**: `LSTMModel`
-   **`parameters`**:
    -   `model_path` (str): The path to the trained LSTM model file (`.pth`).
    -   `seq_len` (int): The length of the input sequence (e.g., how many past time steps to use for prediction).
    -   `input_features` (list): A list of names for the global inputs that will be used as features.
    -   `inflow_names` (list, optional): A list of names of upstream components whose outflows will be used as features.

### `GNNModel`

This component wraps a pre-trained PyTorch GNN model.

-   **`type`**: `GNNModel`
-   **`parameters`**:
    -   `model_path` (str): The path to the trained GNN model file (`.pth`).
    -   `catchment_def_path` (str): The path to the CSV file defining the catchments and their connections.
    -   `target_node_id` (str): The ID (from the catchment definition file) of the node for which this component should predict the flow.
    -   `feature_names` (list): A list of base names for the node features. The component expects global inputs with keys like `{feature_name}_{node_id}`.

## Training the Models

Before you can use the models in a simulation, you need to train them. Training scripts are provided in the `dl_model` directory.

### Training the LSTM Model

To train the LSTM model, run the following command from the project root:

```bash
python3 -m dl_model.train_lstm
```

This will use the data in the `data` directory to train a new model and save it to `dl_model/lstm_model.pth`.

### Training the GNN Model

To train the GNN model, run the following command from the project root:

```bash
python3 -m dl_model.train_gnn
```

This will train a new GNN model and save it to `dl_model/gnn_model.pth`.

## Configuration Example

Here is an example of how to use the `LSTMModel` in a `config.yaml` file:

```yaml
simulation_parameters:
  dt_seconds: 86400
  num_steps: 30

data_sources:
  rainfall_data:
    file: ../../data/rainfall.csv

components:
  - name: LSTM_Flow_Predictor
    type: LSTMModel
    parameters:
      model_path: dl_model/lstm_model.pth
      seq_len: 10
      input_features:
        - rainfall_1
        - rainfall_2
        - rainfall_3

global_inputs:
  - target_component: LSTM_Flow_Predictor
    inputs:
      rainfall_1:
        from_source: rainfall_data
        from_column: rainfall_1
      rainfall_2:
        from_source: rainfall_data
        from_column: rainfall_2
      rainfall_3:
        from_source: rainfall_data
        from_column: rainfall_3

network: []
```

To run this example, you can use the `run_from_config.py` script or the provided example script in `examples/dl_model_example/run_lstm.py`.
