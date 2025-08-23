# Developer Guide

This guide provides a high-level overview of the project structure and includes examples to help developers extend the functionality of the modeling tool.

## 1. Project Structure

The project is organized into several key directories:

-   `common/`: Contains base classes and utilities shared across different modules, such as `BaseModelComponent` and `ConfigParser`.
-   `model_2d/`: Contains the logic for the 2D hydraulic model, including the mesh data structure (`mesh.py`), the finite volume solver (`solver.py`), and the main model component class (`model.py`).
-   `gui/`: Contains all the code for the graphical user interface.
    -   `gui/main.py`: The main Python script for the Eel-based GUI. It handles communication with the frontend and manages the simulation process.
    -   `gui/web/`: The root directory for the web-based frontend.
        -   `gui/web/index.html`: The main HTML file for the application.
        -   `gui/web/style.css`: The main stylesheet for the application.
        -   `gui/web/app.js`: The main JavaScript file for the application logic.
        -   `gui/web/map.js`: The JavaScript file for the 2D map visualization.
-   `examples/`: Contains example scripts that demonstrate how to use the different components of the modeling tool.
-   `docs/`: Contains documentation files, including this guide.

## 2. Backend Development: Adding a New Model Component

To add a new model component, you need to follow these steps:

1.  **Create a new Python module:** Create a new Python file in the appropriate directory (e.g., a new `my_new_model/` directory).
2.  **Create a new model class:** In the new module, create a class that inherits from `common.base_model.BaseModelComponent`.
3.  **Implement the required methods:** The new class must implement the `step` and `get_outflow` methods. It should also have a `get_results` method if it produces data that needs to be visualized.

### Example: A Simple Reservoir Component

Here is an example of a simple reservoir component that stores water and releases it based on a simple rule.

```python
# in my_new_model/reservoir.py
from common.base_model import BaseModelComponent

class Reservoir(BaseModelComponent):
    def __init__(self, name, storage, release_coefficient):
        super().__init__(name)
        self.storage = storage
        self.release_coefficient = release_coefficient
        self.history = []

    def step(self, inflows, dt):
        inflow_volume = sum(inflows.values()) * dt
        self.storage += inflow_volume

        outflow_volume = self.storage * self.release_coefficient * dt
        self.storage -= outflow_volume

        self.outflow = outflow_volume / dt
        self.history.append(self.storage)

    def get_outflow(self):
        return self.outflow

    def get_results(self):
        return {"storage": self.history}
```

## 3. Frontend Development: Extending the UI

The frontend is built using HTML, CSS, and JavaScript. The Eel library is used to communicate with the Python backend.

### Understanding Data Flow

1.  **UI to Backend:** When the user clicks the "Run" button, the `start_simulation` function in `gui/main.py` is called with the current state of the UI.
2.  **Backend to UI:** The backend runs the simulation and, when it's finished, it calls the `simulation_finished` function in `gui/web/app.js`.
3.  **UI requests results:** The `simulation_finished` function then calls the `get_results` function in `gui/main.py` to get the simulation results.
4.  **Backend sends results:** The `get_results` function returns the results as a JSON object.
5.  **UI displays results:** The `render2DResults` function in `gui/web/map.js` is called to display the results on the map.

### Example: Adding a New Plot

To add a new plot to the UI, you would need to:

1.  **Add a new canvas element** to `gui/web/index.html`.
2.  **Add a new function** in `gui/web/app.js` to render the plot. This function would use a library like Chart.js to draw the plot.
3.  **Call the new function** from the `simulation_finished` function, passing it the relevant data from the results object.
