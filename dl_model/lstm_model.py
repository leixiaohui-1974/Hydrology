import torch
import torch.nn as nn
import numpy as np
from collections import deque
from common.base_model import BaseModelComponent

class SimpleLSTM(nn.Module):
    """
    A simple LSTM model for time series forecasting.
    """
    def __init__(self, input_size, hidden_size, num_layers, output_size):
        super(SimpleLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out

class LSTMModel(BaseModelComponent):
    """
    A wrapper for the LSTM model that conforms to the BaseModelComponent interface.
    """
    def __init__(self, name: str, model_path: str, seq_len: int, input_features: list, inflow_names: list = []):
        super().__init__(name)
        self.seq_len = seq_len
        self.input_features = input_features
        self.inflow_names = inflow_names

        # Load the pre-trained model
        self.model = SimpleLSTM(input_size=len(input_features) + len(inflow_names), hidden_size=32, num_layers=2, output_size=1)
        self.model.load_state_dict(torch.load(model_path))
        self.model.eval()  # Set the model to evaluation mode

        self.buffer = deque(maxlen=self.seq_len)
        self.current_global_inputs = {}

    def set_global_inputs(self, inputs: dict):
        """
        Receives global inputs for the current time step.
        """
        self.current_global_inputs = inputs

    def step(self, inflows: dict, dt: float):
        """
        Execute one time step of the LSTM model.
        """
        # 1. Construct the input vector for the current time step
        input_vector = []
        for feature in self.input_features:
            input_vector.append(self.current_global_inputs.get(feature, 0.0))

        for inflow_name in self.inflow_names:
            input_vector.append(inflows.get(inflow_name, 0.0))

        # 2. Add the new input vector to the buffer
        self.buffer.append(input_vector)

        # 3. If we don't have enough data yet, output 0
        if len(self.buffer) < self.seq_len:
            self.outflow = 0.0
            return

        # 4. Prepare the input tensor for the model
        # The buffer contains a list of lists. Convert it to a numpy array first.
        sequence_np = np.array(self.buffer)
        # Reshape for the LSTM: (batch_size, sequence_length, num_features)
        sequence_tensor = torch.FloatTensor(sequence_np).unsqueeze(0)

        # 5. Make a prediction
        with torch.no_grad():
            prediction = self.model(sequence_tensor)

        # 6. Update the outflow
        self.outflow = prediction.item()
