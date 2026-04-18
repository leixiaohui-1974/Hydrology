dl_model package
================

.. automodule:: dl_model
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

dl_model.gnn_model module
-------------------------

.. automodule:: dl_model.gnn_model
   :members:
   :undoc-members:
   :show-inheritance:

dl_model.lstm_model module
--------------------------

.. automodule:: dl_model.lstm_model
   :members:
   :undoc-members:
   :show-inheritance:

dl_model.cnn_model module
-------------------------

.. automodule:: dl_model.cnn_model
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The dl_model package provides deep learning capabilities for the Hydrology Framework.
It implements various neural network architectures for hydrological modeling, including:

* **Graph Neural Networks (GNN)**: For modeling spatial relationships in river networks
* **Long Short-Term Memory (LSTM)**: For time series forecasting and sequence modeling
* **Convolutional Neural Networks (CNN)**: For spatial pattern recognition in gridded data
* **Transformer Models**: For attention-based sequence modeling
* **Physics-Informed Neural Networks (PINN)**: For incorporating physical constraints
* **Hybrid Models**: Combining multiple architectures for complex problems

Key Features
------------

* **Multi-Architecture Support**: GNN, LSTM, CNN, Transformer, and hybrid models
* **Physics-Informed Learning**: Integration of physical laws and constraints
* **Transfer Learning**: Pre-trained models for common hydrological tasks
* **Real-Time Inference**: Optimized models for operational forecasting
* **Uncertainty Quantification**: Bayesian and ensemble methods
* **GPU Acceleration**: CUDA support for training and inference
* **Model Interpretability**: SHAP, LIME, and attention visualization

Key Classes and Functions
-------------------------

GNNModel Class
~~~~~~~~~~~~~~

.. autoclass:: dl_model.gnn_model.GNNModel
   :members:
   :special-members: __init__

SimpleGCN Class
~~~~~~~~~~~~~~~

.. autoclass:: dl_model.gnn_model.SimpleGCN
   :members:
   :special-members: __init__

LSTMModel Class
~~~~~~~~~~~~~~~

.. autoclass:: dl_model.lstm_model.LSTMModel
   :members:
   :special-members: __init__

CNNModel Class
~~~~~~~~~~~~~~

.. autoclass:: dl_model.cnn_model.CNNModel
   :members:
   :special-members: __init__

Usage Examples
--------------

Graph Neural Network for River Network Modeling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.gnn_model import GNNModel, SimpleGCN
   import torch
   import pandas as pd
   import numpy as np
   from torch_geometric.data import Data
   
   # Load catchment data
   catchment_df = pd.read_csv("catchment_data.csv")
   
   # Create GNN model
   gnn_model = GNNModel(
       model_path="models/river_network_gnn.pth",
       catchment_def_path="data/catchment_definition.csv",
       target_node_id="outlet_001",
       feature_names=["precipitation", "temperature", "soil_moisture", "elevation"]
   )
   
   # Prepare graph data
   # Node features: [num_nodes, num_features]
   node_features = torch.tensor([
       [10.5, 15.2, 0.3, 450.0],  # Node 0: precip, temp, soil_moisture, elevation
       [8.2, 16.1, 0.25, 380.0],  # Node 1
       [12.1, 14.8, 0.35, 520.0], # Node 2
       [9.8, 15.5, 0.28, 410.0],  # Node 3
   ], dtype=torch.float32)
   
   # Edge connectivity: [2, num_edges]
   edge_index = torch.tensor([
       [0, 1, 2, 3],  # Source nodes
       [3, 3, 1, 1]   # Target nodes (flow direction)
   ], dtype=torch.long)
   
   # Edge attributes (e.g., channel length, slope)
   edge_attr = torch.tensor([
       [1500.0, 0.002],  # Edge 0->3: length=1500m, slope=0.002
       [2200.0, 0.0015], # Edge 1->3: length=2200m, slope=0.0015
       [800.0, 0.003],   # Edge 2->1: length=800m, slope=0.003
       [1200.0, 0.0025]  # Edge 3->1: length=1200m, slope=0.0025
   ], dtype=torch.float32)
   
   # Create graph data object
   graph_data = Data(
       x=node_features,
       edge_index=edge_index,
       edge_attr=edge_attr
   )
   
   # Train the model
   gnn_model.train_model(
       graph_data=graph_data,
       target_values=torch.tensor([25.5]),  # Target flow at outlet
       epochs=1000,
       learning_rate=0.001,
       batch_size=32
   )
   
   # Make predictions
   with torch.no_grad():
       prediction = gnn_model.predict(graph_data)
       print(f"Predicted flow: {prediction.item():.2f} m³/s")
   
   # Save trained model
   gnn_model.save_model("trained_river_network_gnn.pth")

LSTM for Streamflow Forecasting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.lstm_model import LSTMModel
   import torch
   import numpy as np
   import pandas as pd
   from sklearn.preprocessing import MinMaxScaler
   
   # Load time series data
   data = pd.read_csv("streamflow_data.csv", parse_dates=['date'])
   data.set_index('date', inplace=True)
   
   # Features: precipitation, temperature, previous flows
   features = ['precipitation', 'temperature', 'flow_lag1', 'flow_lag2']
   target = 'flow'
   
   # Normalize data
   feature_scaler = MinMaxScaler()
   target_scaler = MinMaxScaler()
   
   X_scaled = feature_scaler.fit_transform(data[features])
   y_scaled = target_scaler.fit_transform(data[[target]])
   
   # Create sequences for LSTM
   def create_sequences(X, y, sequence_length):
       X_seq, y_seq = [], []
       for i in range(len(X) - sequence_length):
           X_seq.append(X[i:i+sequence_length])
           y_seq.append(y[i+sequence_length])
       return np.array(X_seq), np.array(y_seq)
   
   sequence_length = 30  # 30-day lookback
   X_sequences, y_sequences = create_sequences(X_scaled, y_scaled, sequence_length)
   
   # Split data
   train_size = int(0.8 * len(X_sequences))
   X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
   y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]
   
   # Convert to tensors
   X_train_tensor = torch.FloatTensor(X_train)
   y_train_tensor = torch.FloatTensor(y_train)
   X_test_tensor = torch.FloatTensor(X_test)
   y_test_tensor = torch.FloatTensor(y_test)
   
   # Create LSTM model
   lstm_model = LSTMModel(
       input_size=len(features),
       hidden_size=64,
       num_layers=2,
       output_size=1,
       dropout=0.2,
       bidirectional=True
   )
   
   # Train the model
   lstm_model.train_model(
       X_train=X_train_tensor,
       y_train=y_train_tensor,
       X_val=X_test_tensor,
       y_val=y_test_tensor,
       epochs=200,
       learning_rate=0.001,
       batch_size=64,
       early_stopping_patience=20
   )
   
   # Make predictions
   with torch.no_grad():
       predictions_scaled = lstm_model.predict(X_test_tensor)
       predictions = target_scaler.inverse_transform(predictions_scaled.numpy())
       actual = target_scaler.inverse_transform(y_test)
   
   # Calculate metrics
   from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
   
   mse = mean_squared_error(actual, predictions)
   mae = mean_absolute_error(actual, predictions)
   r2 = r2_score(actual, predictions)
   
   print(f"LSTM Model Performance:")
   print(f"MSE: {mse:.4f}")
   print(f"MAE: {mae:.4f}")
   print(f"R²: {r2:.4f}")
   
   # Plot results
   import matplotlib.pyplot as plt
   
   plt.figure(figsize=(12, 6))
   plt.plot(actual[-100:], label='Actual', alpha=0.7)
   plt.plot(predictions[-100:], label='Predicted', alpha=0.7)
   plt.xlabel('Time Steps')
   plt.ylabel('Streamflow (m³/s)')
   plt.title('LSTM Streamflow Forecasting Results')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()

CNN for Spatial Precipitation Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.cnn_model import CNNModel
   import torch
   import torch.nn as nn
   import numpy as np
   from torch.utils.data import DataLoader, TensorDataset
   
   # Load gridded precipitation data
   # Shape: [num_samples, height, width, channels]
   precipitation_grids = np.load("precipitation_grids.npy")  # [1000, 64, 64, 1]
   runoff_values = np.load("runoff_values.npy")  # [1000, 1]
   
   # Reshape for PyTorch: [num_samples, channels, height, width]
   X = torch.FloatTensor(precipitation_grids).permute(0, 3, 1, 2)
   y = torch.FloatTensor(runoff_values)
   
   # Split data
   train_size = int(0.8 * len(X))
   X_train, X_test = X[:train_size], X[train_size:]
   y_train, y_test = y[:train_size], y[train_size:]
   
   # Create data loaders
   train_dataset = TensorDataset(X_train, y_train)
   test_dataset = TensorDataset(X_test, y_test)
   train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
   test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)
   
   # Create CNN model
   cnn_model = CNNModel(
       input_channels=1,
       input_height=64,
       input_width=64,
       num_classes=1,  # Regression task
       architecture='resnet18'
   )
   
   # Train the model
   cnn_model.train_model(
       train_loader=train_loader,
       val_loader=test_loader,
       epochs=100,
       learning_rate=0.001,
       weight_decay=1e-4
   )
   
   # Evaluate model
   test_loss, test_metrics = cnn_model.evaluate(test_loader)
   print(f"Test Loss: {test_loss:.4f}")
   print(f"Test R²: {test_metrics['r2']:.4f}")
   
   # Visualize feature maps
   sample_input = X_test[0:1]  # Single sample
   feature_maps = cnn_model.get_feature_maps(sample_input)
   
   # Plot feature maps
   import matplotlib.pyplot as plt
   
   fig, axes = plt.subplots(2, 4, figsize=(16, 8))
   for i, (layer_name, features) in enumerate(feature_maps.items()):
       if i >= 8:
           break
       ax = axes[i//4, i%4]
       # Show first channel of feature map
       ax.imshow(features[0, 0].detach().numpy(), cmap='viridis')
       ax.set_title(f'{layer_name}')
       ax.axis('off')
   plt.tight_layout()
   plt.show()

Physics-Informed Neural Network (PINN)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.pinn_model import PINNModel
   import torch
   import torch.nn as nn
   import numpy as np
   
   class HydrologyPINN(PINNModel):
       """Physics-Informed Neural Network for hydrological modeling."""
       
       def __init__(self, layers):
           super().__init__(layers)
           
       def physics_loss(self, x, t, u_pred):
           """Implement conservation of mass for shallow water."""
           # Compute gradients
           u_t = torch.autograd.grad(u_pred, t, 
                                   grad_outputs=torch.ones_like(u_pred),
                                   create_graph=True)[0]
           
           u_x = torch.autograd.grad(u_pred, x,
                                   grad_outputs=torch.ones_like(u_pred),
                                   create_graph=True)[0]
           
           # Shallow water equation: ∂h/∂t + ∂(uh)/∂x = 0
           # Simplified: ∂h/∂t + u∂h/∂x = 0 (assuming constant velocity)
           velocity = 1.0  # m/s (constant for simplicity)
           physics_residual = u_t + velocity * u_x
           
           return torch.mean(physics_residual**2)
       
       def boundary_loss(self, x_boundary, t_boundary, u_boundary_pred, u_boundary_true):
           """Boundary condition loss."""
           return torch.mean((u_boundary_pred - u_boundary_true)**2)
   
   # Create training data
   # Spatial domain: 0 to 10 km
   # Temporal domain: 0 to 24 hours
   x_physics = torch.linspace(0, 10000, 100).reshape(-1, 1).requires_grad_(True)
   t_physics = torch.linspace(0, 86400, 100).reshape(-1, 1).requires_grad_(True)
   
   # Create mesh grid
   X_physics, T_physics = torch.meshgrid(x_physics.squeeze(), t_physics.squeeze())
   x_train = X_physics.reshape(-1, 1).requires_grad_(True)
   t_train = T_physics.reshape(-1, 1).requires_grad_(True)
   
   # Boundary conditions (upstream flow)
   x_boundary = torch.zeros(100, 1)
   t_boundary = torch.linspace(0, 86400, 100).reshape(-1, 1)
   u_boundary = 5.0 * torch.sin(2 * np.pi * t_boundary / 43200)  # 12-hour cycle
   
   # Initial conditions
   x_initial = torch.linspace(0, 10000, 100).reshape(-1, 1)
   t_initial = torch.zeros(100, 1)
   u_initial = torch.zeros(100, 1)  # Initially dry
   
   # Create PINN model
   pinn_model = HydrologyPINN(layers=[2, 50, 50, 50, 1])  # 2 inputs (x,t), 1 output (h)
   
   # Training parameters
   optimizer = torch.optim.Adam(pinn_model.parameters(), lr=0.001)
   
   # Training loop
   for epoch in range(5000):
       optimizer.zero_grad()
       
       # Physics loss
       u_physics_pred = pinn_model(torch.cat([x_train, t_train], dim=1))
       physics_loss = pinn_model.physics_loss(x_train, t_train, u_physics_pred)
       
       # Boundary loss
       u_boundary_pred = pinn_model(torch.cat([x_boundary, t_boundary], dim=1))
       boundary_loss = pinn_model.boundary_loss(x_boundary, t_boundary, 
                                               u_boundary_pred, u_boundary)
       
       # Initial condition loss
       u_initial_pred = pinn_model(torch.cat([x_initial, t_initial], dim=1))
       initial_loss = torch.mean((u_initial_pred - u_initial)**2)
       
       # Total loss
       total_loss = physics_loss + 10 * boundary_loss + 10 * initial_loss
       
       total_loss.backward()
       optimizer.step()
       
       if epoch % 500 == 0:
           print(f"Epoch {epoch}: Total Loss = {total_loss.item():.6f}, "
                 f"Physics = {physics_loss.item():.6f}, "
                 f"Boundary = {boundary_loss.item():.6f}, "
                 f"Initial = {initial_loss.item():.6f}")
   
   # Make predictions
   with torch.no_grad():
       # Create prediction grid
       x_pred = torch.linspace(0, 10000, 50).reshape(-1, 1)
       t_pred = torch.linspace(0, 86400, 50).reshape(-1, 1)
       X_pred, T_pred = torch.meshgrid(x_pred.squeeze(), t_pred.squeeze())
       
       inputs = torch.cat([X_pred.reshape(-1, 1), T_pred.reshape(-1, 1)], dim=1)
       predictions = pinn_model(inputs)
       
       # Reshape for plotting
       water_depths = predictions.reshape(50, 50).numpy()
   
   # Visualize results
   import matplotlib.pyplot as plt
   
   fig, ax = plt.subplots(figsize=(10, 6))
   contour = ax.contourf(X_pred.numpy()/1000, T_pred.numpy()/3600, 
                        water_depths, levels=20, cmap='Blues')
   ax.set_xlabel('Distance (km)')
   ax.set_ylabel('Time (hours)')
   ax.set_title('PINN: Water Depth Evolution')
   plt.colorbar(contour, label='Water Depth (m)')
   plt.show()

Ensemble Model for Uncertainty Quantification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.ensemble_model import EnsembleModel
   from dl_model.lstm_model import LSTMModel
   import torch
   import numpy as np
   
   # Create ensemble of LSTM models
   ensemble_size = 10
   models = []
   
   for i in range(ensemble_size):
       # Create model with slight variations
       model = LSTMModel(
           input_size=4,
           hidden_size=np.random.choice([32, 64, 128]),
           num_layers=np.random.choice([1, 2, 3]),
           output_size=1,
           dropout=np.random.uniform(0.1, 0.3)
       )
       models.append(model)
   
   # Create ensemble
   ensemble_model = EnsembleModel(models)
   
   # Train ensemble with bootstrap sampling
   ensemble_model.train_ensemble(
       X_train=X_train_tensor,
       y_train=y_train_tensor,
       X_val=X_test_tensor,
       y_val=y_test_tensor,
       epochs=100,
       bootstrap_ratio=0.8,  # Use 80% of data for each model
       learning_rate=0.001
   )
   
   # Make predictions with uncertainty
   predictions, uncertainties = ensemble_model.predict_with_uncertainty(X_test_tensor)
   
   # Calculate prediction intervals
   mean_pred = predictions.mean(axis=0)
   std_pred = predictions.std(axis=0)
   
   # 95% confidence intervals
   lower_bound = mean_pred - 1.96 * std_pred
   upper_bound = mean_pred + 1.96 * std_pred
   
   # Plot results with uncertainty
   import matplotlib.pyplot as plt
   
   plt.figure(figsize=(12, 6))
   time_steps = range(len(mean_pred[-100:]))
   
   plt.plot(time_steps, actual[-100:], 'b-', label='Actual', alpha=0.8)
   plt.plot(time_steps, mean_pred[-100:], 'r-', label='Ensemble Mean', alpha=0.8)
   plt.fill_between(time_steps, 
                    lower_bound[-100:], 
                    upper_bound[-100:], 
                    alpha=0.3, color='red', label='95% Confidence Interval')
   
   plt.xlabel('Time Steps')
   plt.ylabel('Streamflow (m³/s)')
   plt.title('Ensemble LSTM with Uncertainty Quantification')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()
   
   # Calculate coverage probability
   coverage = np.mean((actual >= lower_bound) & (actual <= upper_bound))
   print(f"95% Confidence Interval Coverage: {coverage:.3f}")

Transformer Model for Multi-Site Forecasting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.transformer_model import TransformerModel
   import torch
   import torch.nn as nn
   import numpy as np
   
   # Multi-site data: [batch_size, sequence_length, num_sites, num_features]
   num_sites = 5
   sequence_length = 30
   num_features = 3  # precipitation, temperature, flow
   
   # Create transformer model
   transformer_model = TransformerModel(
       input_dim=num_features,
       model_dim=128,
       num_heads=8,
       num_layers=6,
       num_sites=num_sites,
       max_sequence_length=sequence_length,
       dropout=0.1
   )
   
   # Prepare multi-site data
   # Shape: [batch_size, sequence_length, num_sites * num_features]
   X_multisite = torch.randn(1000, sequence_length, num_sites * num_features)
   y_multisite = torch.randn(1000, num_sites)  # Target flows for all sites
   
   # Split data
   train_size = int(0.8 * len(X_multisite))
   X_train_multi = X_multisite[:train_size]
   y_train_multi = y_multisite[:train_size]
   X_test_multi = X_multisite[train_size:]
   y_test_multi = y_multisite[train_size:]
   
   # Train transformer
   transformer_model.train_model(
       X_train=X_train_multi,
       y_train=y_train_multi,
       X_val=X_test_multi,
       y_val=y_test_multi,
       epochs=200,
       learning_rate=0.0001,
       batch_size=32,
       warmup_steps=1000
   )
   
   # Make predictions
   with torch.no_grad():
       predictions_multi = transformer_model.predict(X_test_multi)
   
   # Analyze attention weights
   attention_weights = transformer_model.get_attention_weights(X_test_multi[0:1])
   
   # Visualize attention patterns
   import matplotlib.pyplot as plt
   import seaborn as sns
   
   fig, axes = plt.subplots(2, 4, figsize=(16, 8))
   for head in range(8):
       ax = axes[head//4, head%4]
       # Average attention across layers
       avg_attention = attention_weights[head].mean(dim=0).numpy()
       sns.heatmap(avg_attention, ax=ax, cmap='Blues')
       ax.set_title(f'Attention Head {head+1}')
   plt.tight_layout()
   plt.show()

Model Interpretability and Explainability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.interpretability import ModelInterpreter
   import shap
   import lime
   
   # Create model interpreter
   interpreter = ModelInterpreter(lstm_model)
   
   # SHAP analysis
   explainer = shap.DeepExplainer(lstm_model, X_train_tensor[:100])
   shap_values = explainer.shap_values(X_test_tensor[:10])
   
   # Plot SHAP summary
   shap.summary_plot(shap_values[0], X_test_tensor[:10].numpy(), 
                    feature_names=features)
   
   # Feature importance over time
   feature_importance = interpreter.get_temporal_importance(
       X_test_tensor[:10], 
       method='integrated_gradients'
   )
   
   # Plot temporal importance
   plt.figure(figsize=(12, 6))
   for i, feature in enumerate(features):
       plt.plot(feature_importance[:, i], label=feature)
   plt.xlabel('Time Steps')
   plt.ylabel('Feature Importance')
   plt.title('Temporal Feature Importance')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()
   
   # Sensitivity analysis
   sensitivity = interpreter.sensitivity_analysis(
       X_test_tensor[0:1],
       perturbation_range=0.1
   )
   
   print("Feature Sensitivity:")
   for feature, sens in zip(features, sensitivity):
       print(f"{feature}: {sens:.4f}")

Advanced Features
-----------------

Transfer Learning
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.transfer_learning import PretrainedModels
   
   # Load pre-trained model
   pretrained_model = PretrainedModels.load_model(
       model_type='lstm_streamflow',
       region='temperate',
       resolution='daily'
   )
   
   # Fine-tune for new catchment
   pretrained_model.fine_tune(
       X_new=X_new_catchment,
       y_new=y_new_catchment,
       freeze_layers=['embedding', 'lstm.0'],  # Freeze early layers
       epochs=50,
       learning_rate=0.0001
   )

Federated Learning
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.federated_learning import FederatedTrainer
   
   # Create federated learning setup
   federated_trainer = FederatedTrainer(
       model_class=LSTMModel,
       model_params={
           'input_size': 4,
           'hidden_size': 64,
           'num_layers': 2,
           'output_size': 1
       }
   )
   
   # Add clients (different catchments)
   clients_data = {
       'catchment_A': (X_train_A, y_train_A),
       'catchment_B': (X_train_B, y_train_B),
       'catchment_C': (X_train_C, y_train_C)
   }
   
   # Train federated model
   global_model = federated_trainer.train(
       clients_data=clients_data,
       rounds=100,
       local_epochs=5,
       aggregation_method='fedavg'
   )

Model Compression and Optimization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.optimization import ModelOptimizer
   
   # Create model optimizer
   optimizer = ModelOptimizer(lstm_model)
   
   # Quantization
   quantized_model = optimizer.quantize(
       method='dynamic',
       dtype=torch.qint8
   )
   
   # Pruning
   pruned_model = optimizer.prune(
       sparsity=0.3,  # Remove 30% of weights
       structured=False
   )
   
   # Knowledge distillation
   student_model = LSTMModel(input_size=4, hidden_size=32, num_layers=1, output_size=1)
   distilled_model = optimizer.distill(
       teacher_model=lstm_model,
       student_model=student_model,
       temperature=3.0,
       alpha=0.7
   )
   
   # Compare model sizes and performance
   models = {
       'Original': lstm_model,
       'Quantized': quantized_model,
       'Pruned': pruned_model,
       'Distilled': distilled_model
   }
   
   for name, model in models.items():
       size = optimizer.get_model_size(model)
       inference_time = optimizer.benchmark_inference(model, X_test_tensor[:100])
       print(f"{name}: Size = {size:.2f} MB, Inference = {inference_time:.4f} s")

Configuration and Hyperparameter Tuning
----------------------------------------

Hyperparameter Optimization
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.hyperparameter_tuning import HyperparameterOptimizer
   import optuna
   
   def objective(trial):
       # Define hyperparameter search space
       hidden_size = trial.suggest_categorical('hidden_size', [32, 64, 128, 256])
       num_layers = trial.suggest_int('num_layers', 1, 4)
       dropout = trial.suggest_float('dropout', 0.1, 0.5)
       learning_rate = trial.suggest_loguniform('learning_rate', 1e-5, 1e-2)
       
       # Create and train model
       model = LSTMModel(
           input_size=4,
           hidden_size=hidden_size,
           num_layers=num_layers,
           output_size=1,
           dropout=dropout
       )
       
       # Train model
       val_loss = model.train_model(
           X_train=X_train_tensor,
           y_train=y_train_tensor,
           X_val=X_test_tensor,
           y_val=y_test_tensor,
           epochs=50,
           learning_rate=learning_rate,
           early_stopping_patience=10
       )
       
       return val_loss
   
   # Run optimization
   study = optuna.create_study(direction='minimize')
   study.optimize(objective, n_trials=100)
   
   print(f"Best parameters: {study.best_params}")
   print(f"Best value: {study.best_value:.4f}")

Model Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Model configuration file (YAML)
   model_config = {
       'model_type': 'lstm',
       'architecture': {
           'input_size': 4,
           'hidden_size': 64,
           'num_layers': 2,
           'output_size': 1,
           'dropout': 0.2,
           'bidirectional': True
       },
       'training': {
           'epochs': 200,
           'batch_size': 32,
           'learning_rate': 0.001,
           'weight_decay': 1e-4,
           'early_stopping_patience': 20
       },
       'data': {
           'sequence_length': 30,
           'features': ['precipitation', 'temperature', 'flow_lag1', 'flow_lag2'],
           'target': 'flow',
           'normalization': 'minmax'
       }
   }
   
   # Load model from config
   from dl_model.config import ModelConfig
   
   config = ModelConfig.from_dict(model_config)
   model = config.create_model()

Performance Monitoring and Validation
-------------------------------------

Model Validation
~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.validation import ModelValidator
   
   # Create validator
   validator = ModelValidator()
   
   # Cross-validation
   cv_scores = validator.cross_validate(
       model_class=LSTMModel,
       X=X_sequences,
       y=y_sequences,
       cv_folds=5,
       model_params={
           'input_size': 4,
           'hidden_size': 64,
           'num_layers': 2,
           'output_size': 1
       }
   )
   
   print(f"Cross-validation scores: {cv_scores}")
   print(f"Mean CV score: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")
   
   # Temporal validation (walk-forward)
   temporal_scores = validator.temporal_validation(
       model=lstm_model,
       X=X_sequences,
       y=y_sequences,
       initial_train_size=0.6,
       step_size=0.1
   )
   
   # Plot validation results
   plt.figure(figsize=(10, 6))
   plt.plot(temporal_scores['train_scores'], label='Training Score', marker='o')
   plt.plot(temporal_scores['val_scores'], label='Validation Score', marker='s')
   plt.xlabel('Validation Step')
   plt.ylabel('R² Score')
   plt.title('Temporal Validation Results')
   plt.legend()
   plt.grid(True, alpha=0.3)
   plt.show()

Performance Monitoring
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.monitoring import ModelMonitor
   
   # Create performance monitor
   monitor = ModelMonitor()
   
   # Monitor training progress
   training_metrics = monitor.track_training(
       model=lstm_model,
       train_loader=train_loader,
       val_loader=test_loader,
       metrics=['loss', 'mae', 'r2']
   )
   
   # Plot training curves
   monitor.plot_training_curves(training_metrics)
   
   # Monitor model drift
   drift_detector = monitor.create_drift_detector(
       reference_data=X_train_tensor,
       method='ks_test',
       threshold=0.05
   )
   
   # Check for drift in new data
   drift_detected = drift_detector.detect_drift(X_new_data)
   if drift_detected:
       print("Model drift detected! Consider retraining.")

Deployment and Production
-------------------------

Model Serving
~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.serving import ModelServer
   import torch
   
   # Create model server
   server = ModelServer(
       model=lstm_model,
       preprocessing_pipeline=feature_scaler,
       postprocessing_pipeline=target_scaler
   )
   
   # Start REST API server
   server.start_api(
       host='0.0.0.0',
       port=8000,
       workers=4
   )
   
   # Example API usage:
   # POST /predict
   # {
   #   "features": [[10.5, 15.2, 25.3, 23.1], ...],
   #   "sequence_length": 30
   # }

Batch Inference
~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.inference import BatchInference
   
   # Create batch inference engine
   batch_engine = BatchInference(
       model=lstm_model,
       batch_size=1000,
       device='cuda' if torch.cuda.is_available() else 'cpu'
   )
   
   # Process large dataset
   large_dataset = torch.randn(100000, 30, 4)  # 100k samples
   
   predictions = batch_engine.predict(
       data=large_dataset,
       output_file='predictions.csv',
       progress_bar=True
   )
   
   print(f"Processed {len(predictions)} predictions")

Model Versioning
~~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.versioning import ModelRegistry
   
   # Create model registry
   registry = ModelRegistry(storage_backend='s3')
   
   # Register model
   model_version = registry.register_model(
       model=lstm_model,
       name='streamflow_lstm',
       version='1.0.0',
       metadata={
           'training_data': 'catchment_001_2020_2023',
           'performance': {'r2': 0.85, 'mae': 2.3},
           'features': features,
           'target': target
       }
   )
   
   # Load model by version
   loaded_model = registry.load_model(
       name='streamflow_lstm',
       version='1.0.0'
   )
   
   # List available models
   available_models = registry.list_models()
   print(available_models)

Error Handling and Debugging
----------------------------

Common Issues
~~~~~~~~~~~~~

**Training Issues:**

- Vanishing/exploding gradients
- Overfitting
- Poor convergence
- Memory issues

**Data Issues:**

- Missing values
- Data leakage
- Distribution shift
- Temporal dependencies

**Model Issues:**

- Architecture mismatch
- Hyperparameter sensitivity
- Numerical instability
- Inference speed

Debugging Tools
~~~~~~~~~~~~~~~

.. code-block:: python

   from dl_model.debugging import ModelDebugger
   
   # Create debugger
   debugger = ModelDebugger(lstm_model)
   
   # Check gradients
   gradient_stats = debugger.check_gradients(X_train_tensor, y_train_tensor)
   print(f"Gradient norm: {gradient_stats['norm']:.6f}")
   print(f"Gradient std: {gradient_stats['std']:.6f}")
   
   # Visualize activations
   activations = debugger.get_activations(X_test_tensor[0:1])
   debugger.plot_activation_distribution(activations)
   
   # Check for dead neurons
   dead_neurons = debugger.find_dead_neurons(X_test_tensor)
   print(f"Dead neurons: {dead_neurons}")
   
   # Memory profiling
   memory_usage = debugger.profile_memory(X_test_tensor)
   print(f"Peak memory usage: {memory_usage['peak']:.2f} MB")