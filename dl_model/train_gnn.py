import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler
import numpy as np
from torch_geometric.data import Data
from .gnn_model import SimpleGCN, GNNModel

def main():
    # 1. Load Data
    rainfall_df = pd.read_csv('data/rainfall.csv', index_col='date', parse_dates=True)
    flow_df = pd.read_csv('data/observed_flow.csv', index_col='date', parse_dates=True)
    catchment_df = pd.read_csv('data/catchment_definition.csv')

    # Assume observed flow is at the outlet of the system, which is pfaf_code 1
    target_node_id = '1'

    # 2. Preprocess Data
    # Prepare node features (rainfall)
    # The columns are rainfall_3, rainfall_2, rainfall_1. The pfaf_codes are 3, 2, 1.
    # We will align them.
    node_ids = catchment_df['pfaf_code'].astype(str).tolist()
    feature_df = pd.DataFrame(index=rainfall_df.index)
    for node_id in node_ids:
        feature_df[f'rainfall_{node_id}'] = rainfall_df[f'rainfall_{node_id}']

    # Normalize features
    feature_scaler = MinMaxScaler()
    features_scaled = feature_scaler.fit_transform(feature_df)

    # Normalize labels (flow)
    label_scaler = MinMaxScaler()
    labels_scaled = label_scaler.fit_transform(flow_df[['flow_m3s']])

    # Create a dummy GNNModel instance to reuse its graph building logic
    # We pass dummy values for model_path and feature_names as we don't need them here.
    gnn_model_helper = GNNModel(name="helper", model_path="", catchment_def_path='data/catchment_definition.csv', target_node_id=target_node_id, feature_names=['rainfall'])
    edge_index = gnn_model_helper.graph_data.edge_index
    node_id_to_idx = gnn_model_helper.node_id_to_idx
    target_node_idx = node_id_to_idx[target_node_id]

    # Split data
    train_size = int(len(features_scaled) * 0.8)
    train_features = torch.from_numpy(features_scaled[:train_size]).float()
    train_labels = torch.from_numpy(labels_scaled[:train_size]).float()
    val_features = torch.from_numpy(features_scaled[train_size:]).float()
    val_labels = torch.from_numpy(labels_scaled[train_size:]).float()

    # 3. Define the Model
    num_node_features = len(node_ids)
    model = SimpleGCN(num_node_features=1, hidden_dim=16, num_classes=1)

    # 4. Train the Model
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    num_epochs = 100

    print("--- Starting GNN Model Training ---")
    for epoch in range(num_epochs):
        model.train()
        optimizer.zero_grad()

        # In this simple case, we train on all time steps at once
        # The features need to be reshaped for the GNN
        # We process one time step at a time in a loop
        total_loss = 0
        for i in range(train_size):
            # Node features for this time step: [num_nodes, num_features]
            # Here num_features is 1 (rainfall)
            node_features = train_features[i].view(-1, 1)
            data = Data(x=node_features, edge_index=edge_index)

            outputs = model(data)
            loss = criterion(outputs[target_node_idx], train_labels[i])
            total_loss += loss

        total_loss = total_loss / train_size
        total_loss.backward()
        optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_loss = 0
            for i in range(len(val_features)):
                node_features = val_features[i].view(-1, 1)
                data = Data(x=node_features, edge_index=edge_index)
                val_outputs = model(data)
                val_loss += criterion(val_outputs[target_node_idx], val_labels[i])
            val_loss /= len(val_features)

        if (epoch + 1) % 10 == 0:
            print(f'Epoch [{epoch+1}/{num_epochs}], Loss: {total_loss.item():.4f}, Val Loss: {val_loss.item():.4f}')

    print("--- Finished Training ---")

    # 5. Save the Model
    model_path = 'dl_model/gnn_model.pth'
    torch.save(model.state_dict(), model_path)
    print(f"Model saved to {model_path}")

if __name__ == '__main__':
    main()
