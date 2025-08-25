"""
Parallel Simulation Controller Module
====================================
This module provides the ParallelSimulationController class, which extends
the basic SimulationController with parallel execution capabilities.
"""
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Tuple, Any
import numpy as np
import time
from queue import Queue
import threading
from .controller import SimulationController
from .base_model import BaseModelComponent


class ParallelSimulationController(SimulationController):
    """
    A parallel version of SimulationController that can execute independent
    components simultaneously using multiple processes or threads.
    """
    
    def __init__(self, max_workers: int = None, use_processes: bool = True):
        """
        Initialize the parallel controller.
        
        Args:
            max_workers: Maximum number of worker processes/threads.
                        If None, uses CPU count for processes or 2x CPU count for threads.
            use_processes: If True, use ProcessPoolExecutor for true parallelism.
                          If False, use ThreadPoolExecutor for I/O bound tasks.
        """
        super().__init__()
        self.max_workers = max_workers or (mp.cpu_count() if use_processes else mp.cpu_count() * 2)
        self.use_processes = use_processes
        self.executor = None
        self.parallel_groups = []
        
    def _identify_parallel_groups(self) -> List[List[str]]:
        """
        Identify groups of components that can be executed in parallel.
        Components in the same group have no dependencies on each other.
        """
        if not self.execution_order:
            self._detect_and_sort_components()
            
        parallel_groups = []
        current_group = []
        completed = set()
        
        for component_name in self.execution_order:
            # Check if all parents are completed
            parents = self.parents.get(component_name, [])
            if all(parent in completed for parent in parents):
                current_group.append(component_name)
            else:
                # Start a new group
                if current_group:
                    parallel_groups.append(current_group)
                    completed.update(current_group)
                    current_group = [component_name]
                else:
                    current_group = [component_name]
        
        # Add the last group
        if current_group:
            parallel_groups.append(current_group)
            
        return parallel_groups
    
    def _execute_group_parallel(self, group: List[str], inflows_for_step: Dict) -> Dict[str, Any]:
        """
        Execute a group of components in parallel.
        
        Args:
            group: List of component names to execute in parallel
            inflows_for_step: Input data for the current time step
            
        Returns:
            Dictionary mapping component names to their outputs
        """
        if len(group) == 1:
            # Single component, execute directly
            component_name = group[0]
            return {component_name: self._execute_component(component_name, inflows_for_step)}
        
        # Multiple components, execute in parallel
        futures = {}
        executor_class = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
        
        with executor_class(max_workers=min(len(group), self.max_workers)) as executor:
            # Submit all components in the group
            for component_name in group:
                future = executor.submit(
                    self._execute_component_parallel, 
                    component_name, 
                    inflows_for_step
                )
                futures[future] = component_name
            
            # Collect results
            results = {}
            for future in as_completed(futures):
                component_name = futures[future]
                try:
                    result = future.result()
                    results[component_name] = result
                except Exception as e:
                    print(f"Error executing component {component_name}: {e}")
                    raise
                    
        return results
    
    def _execute_component_parallel(self, component_name: str, inflows_for_step: Dict) -> Any:
        """
        Execute a single component in a separate process/thread.
        This method needs to be picklable for multiprocessing.
        """
        # Recreate the component in the new process/thread
        component = self.components[component_name]
        
        # Gather inflows for this component
        parent_names = self.parents.get(component_name, [])
        component_inflows = inflows_for_step.copy()
        
        for parent_name in parent_names:
            parent_component = self.components[parent_name]
            if hasattr(parent_component, 'get_outflow'):
                component_inflows[parent_name] = parent_component.get_outflow()
        
        # Execute the component
        component.step(component_inflows, dt=1.0)  # dt will be set by the main controller
        return component.get_outflow()
    
    def run_parallel(self, time_steps: int, dt: float, inputs: Dict[str, List[float]] = None) -> Dict[str, List[float]]:
        """
        Run the simulation with parallel execution of independent components.
        
        Args:
            time_steps: Number of time steps to simulate
            dt: Time step duration
            inputs: Dictionary mapping component names to time series of inputs
            
        Returns:
            Dictionary mapping component names to their output time series
        """
        print(f"Starting parallel simulation with {self.max_workers} workers")
        print(f"Using {'processes' if self.use_processes else 'threads'}")
        
        start_time = time.time()
        
        # Initialize results storage
        for component_name in self.components:
            self.results[component_name] = []
        
        # Identify parallel groups
        self.parallel_groups = self._identify_parallel_groups()
        print(f"Identified {len(self.parallel_groups)} parallel execution groups")
        
        # Run simulation
        for step in range(time_steps):
            if step % 100 == 0:
                print(f"Processing time step {step}/{time_steps}")
            
            # Prepare inputs for this time step
            inflows_for_step = {}
            if inputs:
                for component_name, time_series in inputs.items():
                    if step < len(time_series):
                        inflows_for_step[component_name] = time_series[step]
            
            # Execute groups in sequence, but components within each group in parallel
            for group in self.parallel_groups:
                group_results = self._execute_group_parallel(group, inflows_for_step)
                
                # Store results
                for component_name, output in group_results.items():
                    self.results[component_name].append(output)
        
        execution_time = time.time() - start_time
        print(f"Parallel simulation completed in {execution_time:.2f} seconds")
        
        return self.results
    
    def get_parallelization_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the parallelization performance.
        
        Returns:
            Dictionary containing parallelization statistics
        """
        return {
            'max_workers': self.max_workers,
            'use_processes': self.use_processes,
            'parallel_groups': len(self.parallel_groups),
            'group_sizes': [len(group) for group in self.parallel_groups],
            'total_components': len(self.components)
        }


class HybridParallelController(ParallelSimulationController):
    """
    A hybrid controller that automatically chooses between process and thread
    parallelization based on the task characteristics.
    """
    
    def __init__(self, max_workers: int = None):
        super().__init__(max_workers, use_processes=True)
        self.thread_executor = None
        self.process_executor = None
        
    def _classify_component(self, component_name: str) -> str:
        """
        Classify a component as CPU-intensive or I/O-intensive.
        
        Returns:
            'cpu' for CPU-intensive components, 'io' for I/O-intensive
        """
        component = self.components[component_name]
        component_type = type(component).__name__
        
        # CPU-intensive components (numerical computations)
        cpu_intensive = [
            'HydrologicalModel', 'HydraulicModel', 'HydraulicModel2D',
            'SCSCurveNumberModule', 'XinanjiangRunoffModule', 'HymodRunoffModule'
        ]
        
        # I/O-intensive components (data processing, file operations)
        io_intensive = [
            'DataLoader', 'GISProcessor', 'DiagnosticEngine'
        ]
        
        if component_type in cpu_intensive:
            return 'cpu'
        elif component_type in io_intensive:
            return 'io'
        else:
            return 'cpu'  # Default to CPU-intensive
    
    def _execute_group_hybrid(self, group: List[str], inflows_for_step: Dict) -> Dict[str, Any]:
        """
        Execute a group using hybrid parallelization (processes for CPU-intensive,
        threads for I/O-intensive components).
        """
        if len(group) == 1:
            return {group[0]: self._execute_component(group[0], inflows_for_step)}
        
        # Separate components by type
        cpu_components = []
        io_components = []
        
        for component_name in group:
            if self._classify_component(component_name) == 'cpu':
                cpu_components.append(component_name)
            else:
                io_components.append(component_name)
        
        results = {}
        
        # Execute CPU-intensive components with processes
        if cpu_components:
            with ProcessPoolExecutor(max_workers=min(len(cpu_components), self.max_workers)) as executor:
                futures = {
                    executor.submit(self._execute_component_parallel, name, inflows_for_step): name
                    for name in cpu_components
                }
                
                for future in as_completed(futures):
                    component_name = futures[future]
                    try:
                        result = future.result()
                        results[component_name] = result
                    except Exception as e:
                        print(f"Error executing CPU component {component_name}: {e}")
                        raise
        
        # Execute I/O-intensive components with threads
        if io_components:
            with ThreadPoolExecutor(max_workers=min(len(io_components), self.max_workers * 2)) as executor:
                futures = {
                    executor.submit(self._execute_component_parallel, name, inflows_for_step): name
                    for name in io_components
                }
                
                for future in as_completed(futures):
                    component_name = futures[future]
                    try:
                        result = future.result()
                        results[component_name] = result
                    except Exception as e:
                        print(f"Error executing I/O component {component_name}: {e}")
                        raise
        
        return results

