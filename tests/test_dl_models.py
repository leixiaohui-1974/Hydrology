import unittest
import torch
import os
import pandas as pd
from dl_model.lstm_model import LSTMModel, SimpleLSTM
from dl_model.gnn_model import GNNModel, SimpleGCN

class TestDLModels(unittest.TestCase):

    def setUp(self):
        # Create a dummy directory for test artifacts
        self.test_dir = 'tests/temp_test_data'
        os.makedirs(self.test_dir, exist_ok=True)

        # Create a dummy LSTM model file
        self.lstm_model_path = os.path.join(self.test_dir, 'dummy_lstm.pth')
        lstm_model = SimpleLSTM(input_size=2, hidden_size=32, num_layers=2, output_size=1)
        torch.save(lstm_model.state_dict(), self.lstm_model_path)

        # Create a dummy GNN model file
        self.gnn_model_path = os.path.join(self.test_dir, 'dummy_gnn.pth')
        gnn_model = SimpleGCN(num_node_features=1, hidden_dim=16, num_classes=1)
        torch.save(gnn_model.state_dict(), self.gnn_model_path)

        # Create a dummy catchment definition file
        self.catchment_path = os.path.join(self.test_dir, 'dummy_catchment.csv')
        catchment_data = {'pfaf_code': [1, 2], 'downstream_pfaf': [None, 1]}
        pd.DataFrame(catchment_data).to_csv(self.catchment_path, index=False)

    def tearDown(self):
        # Clean up the dummy files and directory
        for f in os.listdir(self.test_dir):
            os.remove(os.path.join(self.test_dir, f))
        os.rmdir(self.test_dir)

    def test_lstm_model_step(self):
        # Instantiate the model
        lstm_comp = LSTMModel(
            name="test_lstm",
            model_path=self.lstm_model_path,
            seq_len=3,
            input_features=['rainfall'],
            inflow_names=['upstream_flow']
        )

        # Simulate a few steps
        for i in range(5):
            lstm_comp.set_global_inputs({'rainfall': 0.5 * i})
            lstm_comp.step(inflows={'upstream_flow': 10.0}, dt=86400)

        # Check that outflow is a float
        self.assertIsInstance(lstm_comp.get_outflow(), float)

    def test_gnn_model_step(self):
        # Instantiate the model
        gnn_comp = GNNModel(
            name="test_gnn",
            model_path=self.gnn_model_path,
            catchment_def_path=self.catchment_path,
            target_node_id='1',
            feature_names=['rainfall']
        )

        # Simulate a step
        gnn_comp.set_global_inputs({'rainfall_1': 5.0, 'rainfall_2': 10.0})
        gnn_comp.step(inflows={}, dt=86400)

        # Check that outflow is a float
        self.assertIsInstance(gnn_comp.get_outflow(), float)

if __name__ == '__main__':
    unittest.main()
