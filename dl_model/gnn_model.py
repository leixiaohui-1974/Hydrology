import torch
import torch.nn as nn
import pandas as pd
import torch_geometric.nn as pyg_nn
from torch_geometric.data import Data
from typing import List, Dict, Any
from common.base_model import BaseModelComponent

class SimpleGCN(nn.Module):
    """
    A simple Graph Convolutional Network (GCN) model.
    """
    def __init__(self, num_node_features: int, hidden_dim: int, num_classes: int) -> None:
        super(SimpleGCN, self).__init__()
        self.conv1: pyg_nn.GCNConv = pyg_nn.GCNConv(num_node_features, hidden_dim)
        self.conv2: pyg_nn.GCNConv = pyg_nn.GCNConv(hidden_dim, num_classes)

    def forward(self, data: Data) -> torch.Tensor:
        x, edge_index = data.x, data.edge_index

        x = self.conv1(x, edge_index)
        x = torch.relu(x)
        x = torch.dropout(x, p=0.5, train=self.training)
        x = self.conv2(x, edge_index)

        return x

class GNNModel(BaseModelComponent):
    """
    A wrapper for the GNN model that conforms to the BaseModelComponent interface.
    """
    def __init__(self, name: str, model_path: str, catchment_def_path: str, target_node_id: str, feature_names: List[str]) -> None:
        super().__init__(name)
        self.model_path: str = model_path
        self.catchment_def_path: str = catchment_def_path
        self.target_node_id: str = str(target_node_id)
        self.feature_names: List[str] = feature_names

        # Load catchment definition and build graph
        self.catchment_df: pd.DataFrame = pd.read_csv(self.catchment_def_path, dtype={'pfaf_code': str, 'downstream_pfaf': str})
        self.node_ids: List[str] = self.catchment_df['pfaf_code'].tolist()
        self.node_id_to_idx: Dict[str, int] = {node_id: i for i, node_id in enumerate(self.node_ids)}

        edge_index: torch.Tensor = self._build_edge_index()
        self.graph_data: Data = Data(edge_index=edge_index)

        # Instantiate or load the model
        num_nodes: int = len(self.node_ids)
        num_features: int = len(self.feature_names)
        self.model: SimpleGCN = SimpleGCN(num_node_features=num_features, hidden_dim=16, num_classes=1)
        self.model.load_state_dict(torch.load(model_path))
        self.model.eval()

        self.current_global_inputs = {}

    def _build_edge_index(self):
        sources = []
        targets = []
        for _, row in self.catchment_df.iterrows():
            if pd.notna(row['downstream_pfaf']) and row['downstream_pfaf'] != '':
                downstream_id = row['downstream_pfaf']
                if downstream_id in self.node_id_to_idx:
                    sources.append(self.node_id_to_idx[row['pfaf_code']])
                    targets.append(self.node_id_to_idx[downstream_id])

        return torch.tensor([sources, targets], dtype=torch.long)

    def set_global_inputs(self, inputs: dict):
        """
        Receives global inputs for the current time step.
        """
        self.current_global_inputs = inputs

    def step(self, inflows: dict, dt: float):
        """
        Execute one time step of the GNN model.
        """
        # 1. Construct the node feature matrix `x`
        num_nodes = len(self.node_ids)
        num_features = len(self.feature_names)
        x = torch.zeros((num_nodes, num_features))

        for i, node_id in enumerate(self.node_ids):
            for j, feature_name in enumerate(self.feature_names):
                # Construct the expected key in global_inputs, e.g., "rainfall_3"
                input_key = f"{feature_name}_{node_id}"
                if input_key in self.current_global_inputs:
                    x[i, j] = self.current_global_inputs[input_key]

        self.graph_data.x = x

        # 2. Make a prediction
        with torch.no_grad():
            predictions = self.model(self.graph_data)

        # 3. Extract the prediction for the target node
        if self.target_node_id in self.node_id_to_idx:
            target_idx = self.node_id_to_idx[self.target_node_id]
            self.outflow = predictions[target_idx].item()
        else:
            self.outflow = 0.0
