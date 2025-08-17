# Rapid Modeling Tool - GUI Manual

## 1. Introduction

Welcome to the Rapid Water Modeling Tool! This tool provides a graphical user interface (GUI) to visually build, run, and analyze complex, coupled water system models.

Instead of writing code or manually creating configuration files, you can use this interface to drag-and-drop components, connect them into a network, and run a simulation with real-time feedback.

## 2. Getting Started

To launch the graphical interface, run the following command from the root directory of the project:

```bash
python3 gui/main.py
```

This will open the main application window.

## 3. The Interface

The GUI is divided into three main panels, plus a results area at the bottom.

### 3.1. Left: Component Palette

This panel contains all the available building blocks for your model.

-   **🏞️ Catchment:** A hydrological component that generates runoff from rainfall.
-   **🌊 River Reach:** A 1D hydraulic model for a river segment.
-   **➕ Junction:** A node to merge or split flows.
-   **⛕ Gate:** A gate structure to control flow within a river.
-   **ポンプ Pump:** A pump to add energy (head) to the flow.

**To use:** Click and drag any component from this palette and drop it onto the central Network Canvas.

### 3.2. Center: Network Canvas

This is your main workspace.

-   **Placing Nodes:** Drag components from the palette to place them on the canvas as nodes. Each node will be given a default unique name (e.g., `RiverReach_1`).
-   **Connecting Nodes:** To connect two nodes (e.g., from a Catchment to a River), use the two-click method:
    1.  Click once on the **source** node (e.g., the Catchment). It will be highlighted with a red border.
    2.  Click a second time on the **target** node (e.g., the River). An arrow will be drawn, representing the flow of water.

### 3.3. Right: Properties Pane

This pane is context-sensitive and allows you to edit the parameters of your model.

-   **Selecting a Node:** Click on any node on the canvas. It will be highlighted in green, and its parameters will appear in the Properties Pane.
-   **Editing Parameters:** You can change any value in the input fields (e.g., `slope`, `manning_n`, `CN`). The changes are stored automatically. The name of the component can also be changed here.
-   **Global Settings:** When no node is selected, this pane will show global simulation settings and post-simulation plotting controls.

## 4. Running a Simulation

1.  **Build your network** on the canvas as described above.
2.  **Click the "Run" button** in the top-left panel.
3.  The simulation will start. For this demonstration, it runs a hard-coded example configuration (`examples/config_coupled.yaml`).

### Real-time Feedback

While the simulation is running, you can monitor its progress in the bottom section of the window:

-   **Chart Panel (Left):** Shows a live plot of the outflow from the final component in the network.
-   **Log Panel (Right):** Displays a step-by-step log of the simulation's progress.

## 5. Analyzing Results

After the simulation finishes successfully:

1.  The **plotting controls** will appear in the top-right pane.
2.  **Select a Component:** Use the first dropdown to choose which component you want to inspect (e.g., `R1_main_river`).
3.  **Select a Variable:** The second dropdown will automatically populate with the variables available for that component (e.g., `Q`, `Z`, `outflow`).
4.  **Click "Plot Selected":** The chart at the bottom will update to show the full time-series for the selected data. For variables with multiple nodes (like `Q` and `Z` in a river), it will plot the data for the last node.

## 6. Saving Your Work

1.  After building your network and setting all parameters in the GUI, click the **"Save" button**.
2.  This will call the Python backend to transform your visual model into the YAML configuration format.
3.  A file named `gui_output_config.yaml` will be saved in the root directory of the project. This file can then be used by the `run_from_config.py` script.
