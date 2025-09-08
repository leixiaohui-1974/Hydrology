"""
PySWMM-like Object Wrappers for Hydro-Suite Components
======================================================

This module provides wrapper classes for the various components within the
Hydro-Suite engine (e.g., Junctions, Reaches, Runoff modules). These
wrappers expose component properties and results in a user-friendly,
`pyswmm`-like interface.
"""
from collections.abc import Mapping
from typing import Any, Iterator, Dict, Optional

# Import the actual component classes to check their types
from common.base_model import BaseModelComponent
from common.junction import Junction
from hydro_model.model import HydrologicalModel
from preissmann_model.model import HydraulicModel
from preissmann_model.structures import Gate


# --- Individual Component Wrappers ---

class Subcatchment:
    """
    A wrapper for a subcatchment component (`HydrologicalModel`) in the simulation.
    Provides access to subcatchment-specific properties and results.
    """
    def __init__(self, component: HydrologicalModel):
        self._component = component

    @property
    def runoff(self) -> float:
        """Gets the runoff from the subcatchment at the current timestep."""
        return self._component.get_outflow()

    @property
    def area(self) -> float:
        """Gets the area of the subcatchment."""
        return getattr(self._component, 'area', 0.0)

    # We can add more properties by inspecting the HydrologicalModel,
    # e.g., to get the parameters of the runoff module.


class Node:
    """
    A wrapper for a node-like component (a `Junction`) in the simulation.
    Provides access to node-specific properties and results.
    """
    def __init__(self, component: Junction):
        self._component = component

    @property
    def total_inflow(self) -> float:
        """Gets the total inflow to the node at the current timestep."""
        return self._component.get_total_inflow()

    @property
    def depth(self) -> float:
        """Gets the water depth at the node."""
        return getattr(self._component, 'depth', 0.0)


class Link:
    """
    A wrapper for a link-like component (e.g., `HydraulicModel`) in the simulation.
    Provides access to link-specific properties, results, and controls.
    """
    def __init__(self, component: BaseModelComponent):
        self._component = component
        self._gate: Optional[Gate] = None

        # Check if this link contains a controllable gate
        if isinstance(self._component, HydraulicModel) and self._component.structures:
            for struct in self._component.structures:
                if isinstance(struct, Gate):
                    self._gate = struct
                    break

    @property
    def flow(self) -> float:
        """Gets the flow in the link at the current timestep."""
        return self._component.get_outflow()

    @property
    def target_setting(self) -> Optional[float]:
        """
        Gets the target setting of a controllable element in the link.
        For a gate, this is the opening height.
        """
        if self._gate:
            return self.opening_height
        return None

    @target_setting.setter
    def target_setting(self, value: float):
        """
        Sets the target setting of a controllable element in the link.
        For a gate, this sets the opening height.
        """
        if self._gate:
            self.opening_height = value
        else:
            print(f"Warning: Link '{self._component.name}' has no controllable gate to set.")

    # --- Gate-specific properties for convenience ---
    @property
    def opening_height(self) -> Optional[float]:
        """Gets the opening height if the link contains a gate."""
        if self._gate:
            return self._gate.opening_height
        return None

    @opening_height.setter
    def opening_height(self, height: float):
        """Sets the opening height if the link contains a gate."""
        if self._gate:
            self._gate.opening_height = height
        else:
            print(f"Warning: Link '{self._component.name}' has no gate.")


# --- Collection Accessor Classes ---

class Subcatchments(Mapping):
    """A dictionary-like collection of all subcatchment components."""
    def __init__(self, sim: Any):
        self._sim = sim
        self._subcatchments: Dict[str, Subcatchment] = {
            name: Subcatchment(comp)
            for name, comp in self._sim._controller.components.items()
            if isinstance(comp, HydrologicalModel)
        }

    def __getitem__(self, key: str) -> Subcatchment:
        return self._subcatchments[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._subcatchments)

    def __len__(self) -> int:
        return len(self._subcatchments)


class Nodes(Mapping):
    """A dictionary-like collection of all node components."""
    def __init__(self, sim: Any):
        self._sim = sim
        self._nodes: Dict[str, Node] = {
            name: Node(comp)
            for name, comp in self._sim._controller.components.items()
            if isinstance(comp, Junction)
        }

    def __getitem__(self, key: str) -> Node:
        return self._nodes[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)


class Links(Mapping):
    """A dictionary-like collection of all link components."""
    def __init__(self, sim: Any):
        self._sim = sim
        # A "Link" is any component that is not a Subcatchment or a Node.
        self._links: Dict[str, Link] = {
            name: Link(comp)
            for name, comp in self._sim._controller.components.items()
            if not isinstance(comp, (HydrologicalModel, Junction))
        }

    def __getitem__(self, key: str) -> Link:
        return self._links[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._links)

    def __len__(self) -> int:
        return len(self._links)
