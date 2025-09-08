"""
PySWMM-like Wrapper for the Hydro-Suite Simulation Engine
=========================================================

This module provides a high-level, user-friendly API to interact with
the Hydro-Suite modeling framework. The design of this API is heavily
inspired by PySWMM to provide a familiar interface for users.
"""
from common.config_parser import ConfigParser
import datetime
from .objects import Nodes, Links, Subcatchments


class Simulation:
    """
    A PySWMM-like simulation object that wraps the Hydro-Suite controller.

    This class allows for a `pyswmm`-style interaction with a simulation
    defined in a Hydro-Suite YAML configuration file.

    Examples:
        >>> with Simulation('config.yaml') as sim:
        ...     for step in sim:
        ...         print(sim.current_time)
    """
    def __init__(self, config_file: str):
        """
        Initializes the simulation from a YAML configuration file.

        Args:
            config_file (str): Path to the simulation configuration file.
        """
        self._config_file = config_file
        print(f"--- Loading configuration from: {self._config_file} ---")
        try:
            parser = ConfigParser(self._config_file)
            self._controller, self._sim_params, self._global_inputs = parser.build_simulation()
        except Exception as e:
            print(f"Error building simulation from config file: {e}")
            raise

        self._dt_seconds = self._sim_params.get('dt_seconds', 60)
        self._num_steps = self._sim_params.get('num_steps', 1)
        self._start_time_str = self._sim_params.get('start_time', "2020-01-01 00:00:00")

        self._start_time = datetime.datetime.strptime(self._start_time_str, "%Y-%m-%d %H:%M:%S")
        self._current_time = self._start_time
        self._step_iter = None
        self._current_step = 0

        # Lazily initialized accessor objects
        self._nodes: Optional[Nodes] = None
        self._links: Optional[Links] = None
        self._subcatchments: Optional[Subcatchments] = None

    @property
    def nodes(self) -> Nodes:
        """
        Get a dictionary-like object of all nodes in the simulation.
        """
        if self._nodes is None:
            self._nodes = Nodes(self)
        return self._nodes

    @property
    def links(self) -> Links:
        """
        Get a dictionary-like object of all links in the simulation.
        """
        if self._links is None:
            self._links = Links(self)
        return self._links

    @property
    def subcatchments(self) -> Subcatchments:
        """
        Get a dictionary-like object of all subcatchments in the simulation.
        """
        if self._subcatchments is None:
            self._subcatchments = Subcatchments(self)
        return self._subcatchments

    def __enter__(self):
        """
        Enter the runtime context related to this object.
        """
        print("--- Starting Simulation Context ---")
        # In pyswmm, this would open the swmm toolkit. Here, we just return self.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context related to this object.
        """
        # In pyswmm, this closes the swmm toolkit. Here, we can perform cleanup.
        print("--- Closing Simulation Context ---")
        pass

    def __iter__(self):
        """
        Initialize the simulation iterator.
        """
        print("--- Initializing Simulation Iterator ---")
        self._step_iter = self._controller.run(
            num_steps=self._num_steps,
            dt=self._dt_seconds,
            global_inputs=self._global_inputs
        )
        self._current_step = 0
        # Reset time to start time before iteration begins
        self._current_time = self._start_time
        return self

    def __next__(self):
        """
        Advance the simulation by one step.
        """
        if self._current_step >= self._num_steps:
            raise StopIteration

        # Advance the simulation by calling next on the generator
        status = next(self._step_iter)

        # Update current time and step count
        if self._current_step > 0: # Time is already at start for the first step
             self._current_time += datetime.timedelta(seconds=self._dt_seconds)

        self._current_step += 1

        # In pyswmm, the iterator yields nothing, but the user can access properties.
        # We will do the same. The `status` from the controller run can be stored if needed.
        # This makes the loop body execute after the step is completed.
        return

    @property
    def current_time(self) -> datetime.datetime:
        """
        Returns the current simulation time. This represents the time at the
        *beginning* of the current simulation step.
        """
        return self._current_time
