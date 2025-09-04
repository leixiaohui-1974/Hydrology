from typing import List, Any

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

# Forward-declare types to avoid circular imports
# These are just for type hinting and not strictly necessary for functionality
if 'preissmann_model.model' not in locals():
    from typing import Type
    HydraulicModel = Type['preissmann_model.model.HydraulicModel']
if 'model_2d.model' not in locals():
    from typing import Type
    Model2D = Type['model_2d.model.Model2D']


class LateralWeirLink:
    """
    Represents a lateral connection between a 1D river reach and a 2D model area,
    simulating flow over a broad-crested weir (e.g., a river bank).
    """
    def __init__(self, name: str, model_1d: Any, model_2d: Any,
                 reach_id: str, node_idx_1d: int, edge_ids_2d: List[int],
                 weir_coeff: float = 1.6, bank_elevation: float = 10.0) -> None:
        """
        Initializes the lateral link.

        Args:
            name (str): A unique name for the link.
            model_1d (HydraulicModel): The 1D hydraulic model component.
            model_2d (Model2D): The 2D model component.
            reach_id (str): The name of the specific reach within the 1D model.
            node_idx_1d (int): The index of the node in the 1D reach to link from.
            edge_ids_2d (list[int]): A list of boundary edge IDs in the 2D mesh to link to.
            weir_coeff (float): The discharge coefficient for the weir formula.
            bank_elevation (float): The elevation of the river bank or levee crest.
        """
        self.name: str = name
        self.model_1d: Any = model_1d
        self.model_2d: Any = model_2d
        self.reach_id: str = reach_id # Note: model_1d might contain multiple reaches
        self.node_idx_1d: int = node_idx_1d
        self.edge_ids_2d: List[int] = edge_ids_2d

        self.weir_coeff: float = weir_coeff
        self.bank_elevation: float = bank_elevation



        # For storing the latest calculated flow
        self.exchange_flow: float = 0.0
        self.length: float = sum(self.model_2d.mesh.edges[edge_id].length for edge_id in self.edge_ids_2d)

    def calculate_exchange_flow(self) -> float:
        """
        Calculates the flow between the 1D and 2D models based on water levels.
        The flow is positive when moving from 1D to 2D.
        """
        # 1. Get water surface elevation from the 1D model
        # This assumes the HydraulicModel has a way to get water level at a specific node
        # We will need to implement this. For now, let's assume it exists.
        w_1d = self.model_1d.get_water_level_at_node(self.node_idx_1d)

        # 2. Get an average water surface elevation from the 2D model
        # This is the average water level in the faces adjacent to the connected edges.
        total_w_2d = 0
        num_faces = 0
        for edge_id in self.edge_ids_2d:
            edge = self.model_2d.mesh.edges[edge_id]
            # The connected face must be face1, as face2 is None for boundary edges
            face = edge.face1
            total_w_2d += (face.h + face.z_bed)
            num_faces += 1

        w_2d = total_w_2d / num_faces if num_faces > 0 else self.bank_elevation

        # 3. Apply the weir formula
        q = 0.0
        if w_1d > self.bank_elevation and w_1d > w_2d:
            # Flow from 1D to 2D
            H = w_1d - self.bank_elevation
            q = self.weir_coeff * self.length * H**1.5
        elif w_2d > self.bank_elevation and w_2d > w_1d:
            # Flow from 2D to 1D (negative sign)
            H = w_2d - self.bank_elevation
            q = - (self.weir_coeff * self.length * H**1.5)

        self.exchange_flow = q
        return q

    def update_models(self) -> None:
        """
        Applies the calculated exchange flow to the respective models.
        This would be called by the controller after calculate_exchange_flow.
        """
        # This is a placeholder for the logic that will add/remove water.
        # The actual implementation will be in the step() methods of the models.
        # For example:
        # self.model_1d.add_source_term_at_node(self.node_idx_1d, -self.exchange_flow)
        # self.model_2d.add_source_term_at_edges(self.edge_ids_2d, self.exchange_flow)
        pass
