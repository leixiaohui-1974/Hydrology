# Tutorial: Ultimate Case Study - A Fully Integrated Model

This tutorial demonstrates the full power of the Rapid Modeling Framework by building, running, and analyzing a complex, multi-component model.

## 1. The Scenario

We will model a river basin that includes hydrological, 1D hydraulic, and 2D hydraulic components, all coupled together. The system consists of:
- A **headwater catchment** that generates runoff.
- An **inflow river** that carries this runoff to a split.
- A **junction** that splits the flow into two main branches:
    - A **main channel** which is regulated by a **gate**.
    - A smaller **bypass channel**.
- A second **junction** where the two branches merge back together.
- A **final river reach** that carries the combined flow.
- A **2D floodplain** that can interact with the final river reach (Note: this part is conceptual as the 1D-2D link is not yet implemented).

This scenario uses almost every feature we have built.

## 2. Building the Model

Because this model is so complex, building it entirely through the GUI and saving it is the recommended workflow. However, to run this specific case study, we will use the pre-built configuration file located at `examples/ultimate_case_study/config.yaml`.

### A Note on the 2D Model

The `ConfigParser` currently cannot create the 2D model's mesh from the YAML file. To run this case study, you would need to modify the `run_from_config.py` script to manually create the `Mesh` and `Model2D` objects and add them to the controller. This is an advanced step that highlights a current limitation and an area for future development.

For this tutorial, we will focus on the 1D network defined in the configuration file.

## 3. Running the Simulation

1.  **Open `run_from_config.py`** in your editor.
2.  **Ensure it is pointing to the correct configuration file:**
    ```python
    # In the main() function of run_from_config.py
    config_file = "examples/ultimate_case_study/config.yaml"
    ```
    (You may need to modify the script to use a fixed path instead of a command-line argument for simplicity).
3.  **Run the script** from the project's root directory:
    ```bash
    python3 run_from_config.py examples/ultimate_case_study/config.yaml
    ```
4.  **Alternatively, use the GUI:**
    -   Launch the GUI with `python3 gui/main.py`.
    -   Modify the `handleRun` function in `gui/web/app.js` to point to the correct config file path.
    -   Click the "Run" button.

## 4. Analyzing the Results

After the simulation completes, you can use the **Plotting Controls** in the GUI to explore the behavior of the complex network.

-   **Check the Junctions:**
    -   Plot the `outflow` of `J1_split`.
    -   Plot the `outflow` of `R2A_main_channel` and `R2B_bypass_channel`. You will see that the sum of these two is roughly equal to the inflow to the junction (minus channel storage effects). The split will not be exactly 60/40 because it's based on the initial split of outflow, and the downstream hydraulic conditions will affect the final flows.
-   **Analyze the Gate:**
    -   Plot the `Z` (water level) for `R2A_main_channel`. You can see the effect of the gate causing water to back up.
-   **Verify Mass Balance:**
    -   Plot the `outflow` of `J2_merge`. This should be approximately the sum of the final outflows of `R2A_main_channel` and `R2B_bypass_channel`.

This comprehensive case study demonstrates how the different components of the framework can be connected to build and simulate sophisticated, real-world water resource systems.
