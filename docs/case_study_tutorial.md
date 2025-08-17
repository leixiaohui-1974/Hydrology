# Tutorial: Building a Comprehensive Case Study

This tutorial will walk you through using the **Rapid Modeling Tool GUI** to build, run, and analyze a complete water system model.

## 1. The Scenario

We will model a small river basin with the following characteristics:
- An **upper catchment** area that flows into an **upstream river** reach.
- A **tributary catchment** that also contributes flow.
- The upstream river and the tributary catchment both flow into a **junction**.
- The merged flow continues into a long **downstream river**.
- A **control gate** is situated in the middle of the downstream river to manage water levels.
- The entire system is driven by a single **rainfall event**.

This scenario demonstrates the tool's ability to couple hydrological and hydraulic components, handle network junctions, and simulate hydraulic structures.

## 2. Building the Model in the GUI

### Step 2.1: Launch the GUI

Open your terminal in the project's root directory and run:
```bash
python3 gui/main.py
```

### Step 2.2: Place the Components

Drag the following components from the **Component Palette** (left pane) onto the **Network Canvas** (center pane):
- 2 x **Catchment**
- 2 x **River Reach**
- 1 x **Junction**
- 1 x **Gate**

Arrange them logically on the canvas, similar to the diagram above.

### Step 2.3: Set Component Properties

Click on each node on the canvas and use the **Properties Pane** (right pane) to set its name and parameters.

1.  **First Catchment:**
    -   Name: `upper_catchment`
    -   CN: `80`
2.  **Second Catchment:**
    -   Name: `tributary_catchment`
    -   CN: `70`
3.  **First River Reach:**
    -   Name: `upstream_river`
    -   Slope: `0.002`
    -   Manning n: `0.04`
    -   Length: `10000`
    -   Width: `50`
4.  **Junction:**
    -   Name: `main_junction`
5.  **Second River Reach:**
    -   Name: `downstream_river`
    -   Slope: `0.001`
    -   Manning n: `0.035`
    -   Length: `20000`
    -   Width: `60`
6.  **Gate:**
    -   Name: `control_gate`
    -   Opening Height: `1.0`
    -   Width: `60`

*(Note: For this tutorial, we will not place the gate inside the river via the GUI, as that functionality is complex. The final `config.yaml` shows how it would be configured manually.)*

### Step 2.4: Connect the Network

Use the two-click method to draw connections (arrows) between the nodes:
1.  Connect `upper_catchment` -> `upstream_river`.
2.  Connect `upstream_river` -> `main_junction`.
3.  Connect `tributary_catchment` -> `main_junction`.
4.  Connect `main_junction` -> `downstream_river`.

## 3. Saving and Running the Simulation

### Step 3.1: Save the Configuration

Click the **"Save"** button in the top-left panel. This will generate a `gui_output_config.yaml` file in your project directory. It should look very similar to the pre-built `examples/full_case_study/config.yaml`.

### Step 3.2: Run the Simulation

For this tutorial, we will use the pre-built configuration file which correctly places the gate inside the downstream river.

1.  In `gui/main.py`, make sure the `start_simulation` function points to the correct config file:
    ```python
    eel.start_simulation('examples/full_case_study/config.yaml')
    ```
2.  Launch the GUI and click the **"Run"** button.
3.  Observe the **Live Log** and **Live Chart** to see the simulation progress in real-time.

## 4. Analyzing the Results

Once the simulation is complete, the **Plotting Controls** will appear in the top-right pane.

-   **Analyze the Junction:**
    1.  Select `main_junction` from the component dropdown.
    2.  Select `outflow` from the variable dropdown and click **"Plot Selected"**. This shows the total flow entering the downstream river.
-   **Analyze the Gate's Effect:**
    1.  Select `downstream_river` from the component dropdown.
    2.  Select `Z` from the variable dropdown and click **"Plot Selected"**. You will see the water surface elevation at the last node of the river.
    3.  *(To see the full profile, you would need to export the results to CSV and plot them in another tool, as the GUI currently only plots the last node).*
    4.  Notice how the water level upstream of the gate (around nodes 4-5) would be higher than downstream, showing its impounding effect.

This completes the case study, demonstrating the full workflow of the Rapid Modeling Tool.
