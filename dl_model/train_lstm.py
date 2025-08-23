import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import MinMaxScaler
import numpy as np
from .lstm_model import SimpleLSTM

def create_sequences(data, seq_length):
    xs, ys = [], []
    for i in range(len(data) - seq_length):
        x = data[i:i+seq_length, :-1]
        y = data[i+seq_length, -1]
        xs.append(x)
        ys.append(y)
    return np.array(xs), np.array(ys)

def main():
    # 1. Load Data
    rainfall_df = pd.read_csv('data/rainfall.csv', index_col='date', parse_dates=True)
    flow_df = pd.read_csv('data/observed_flow.csv', index_col='date', parse_dates=True)

    # Use all three rainfall columns as features
    data_df = rainfall_df.copy()
    data_df['flow'] = flow_df['flow_m3s']

    # 2. Preprocess Data
    scaler = MinMaxScaler()
    data_scaled = scaler.fit_transform(data_df)

    seq_length = 10 # Use 10 days of data to predict the next day's flow
    X, y = create_sequences(data_scaled, seq_length)

    X_tensor = torch.from_numpy(X).float()
    y_tensor = torch.from_numpy(y).float().view(-1, 1)

    # Split into training and validation sets
    train_size = int(len(X) * 0.8)
    X_train, X_val = X_tensor[:train_size], X_tensor[train_size:]
    y_train, y_val = y_tensor[:train_size], y_tensor[train_size:]

    train_dataset = TensorDataset(X_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)

    # 3. Define the Model
    input_size = X_train.shape[2] # number of features
    hidden_size = 32
    num_layers = 2
    output_size = 1
    model = SimpleLSTM(input_size, hidden_size, num_layers, output_size)

    # 4. Train the Model
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    num_epochs = 50

    print("--- Starting LSTM Model Training ---")
    for epoch in range(num_epochs):
        model.train()
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_loss = criterion(val_outputs, y_val)

        if (epoch + 1) % 10 == 0:
            print(f'Epoch [{epoch+1}/{num_epochs}], Loss: {loss.item():.4f}, Val Loss: {val_loss.item():.4f}')

    print("--- Finished Training ---")

    # 5. Save the Model
    model_path = 'dl_model/lstm_model.pth'
    torch.save(model.state_dict(), model_path)
    print(f"Model saved to {model_path}")

if __name__ == '__main__':
    main()
