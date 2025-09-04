"""
Junction Component Module
=========================

This module provides the Junction class, which acts as a node for
merging and splitting flows in a model network.
"""
from typing import Dict, List, Optional, Union
from .base_model import BaseModelComponent

class Junction(BaseModelComponent):
    """
    A Junction component merges multiple inflows and splits the total flow
    to multiple outflows based on specified rules.

    This implementation primarily enforces conservation of mass.
    """
    def __init__(self, name: str, split_rules: Optional[Dict[str, float]] = None) -> None:
        """
        Initializes the Junction.

        Args:
            name (str): The unique name of the junction.
            split_rules (Dict[str, float], optional):
                A dictionary where keys are the names of downstream components
                and values are the fraction of total flow to distribute to them.
                The sum of fractions should be 1.0. If not provided, outflow
                is split evenly among all downstream connections.
        """
        super().__init__(name)
        self.split_rules: Optional[Dict[str, float]] = split_rules
        self.total_inflow: float = 0.0
        # This will hold the calculated outflows for each downstream branch
        self.outflows: Dict[str, float] = {}

    def step(self, inflows: Dict[str, Union[float, int]], dt: float) -> None:
        """
        For a junction, a step involves summing inflows and calculating
        the distribution of outflows for the next step.
        """
        self.total_inflow = sum(inflows.values())

        # The junction's primary `outflow` attribute is the total flow.
        self.outflow = self.total_inflow

        # Note: The distribution of this outflow to downstream branches
        # will be handled by a new `get_outflows` method, which the
        # controller will need to be updated to use.
        pass

    def get_outflows(self, downstream_connections: List[str]) -> Dict[str, float]:
        """
        Calculates and returns the split outflows for all downstream components.

        Args:
            downstream_connections (List[str]): A list of the names of the
                                                components connected downstream.

        Returns:
            A dictionary where keys are the downstream component names and
            values are their respective calculated inflows.
        """
        if not downstream_connections:
            return {}

        if self.split_rules:
            # Apply user-defined split rules
            total_fraction = sum(self.split_rules.values())
            if abs(total_fraction - 1.0) > 1e-6:
                print(f"Warning: Split rule fractions for Junction '{self.name}' do not sum to 1.0.")

            for branch_name, fraction in self.split_rules.items():
                if branch_name in downstream_connections:
                    self.outflows[branch_name] = self.total_inflow * fraction
                else:
                    # This rule is for a branch not connected, set its flow to 0
                    self.outflows[branch_name] = 0.0
        else:
            # Default to even splitting if no rules are provided
            num_branches = len(downstream_connections)
            split_flow = self.total_inflow / num_branches if num_branches > 0 else 0
            for branch_name in downstream_connections:
                self.outflows[branch_name] = split_flow

        return self.outflows
