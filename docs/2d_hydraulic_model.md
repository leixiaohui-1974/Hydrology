# 2D Hydraulic Model (`model_2d`)

The `model_2d` component provides a proof-of-concept, two-dimensional hydraulic model for simulating depth-averaged shallow water flows on an unstructured triangular mesh.

## Feature Overview

- **Numerical Scheme:** The model uses a first-order accurate **Finite Volume** method with a **Rusanov flux** scheme to solve the 2D Shallow Water Equations.
- **Unstructured Mesh:** It operates on a flexible triangular mesh, allowing it to model complex geometries.
- **Boundary Conditions:** The model now supports configurable boundary conditions, moving it beyond a simple proof-of-concept.

## Mesh File Format

The model requires a mesh defined in a JSON file. This file must contain two keys:
- `points`: A list of `[x, y]` coordinates for each node in the mesh.
- `triangles`: A list of `[node_id_1, node_id_2, node_id_3]` lists, defining the connectivity of the triangular faces.

A utility script is provided to help generate a simple channel mesh in this format:
```bash
python3 utils/create_channel_mesh.py --output_path path/to/your/mesh.json
```
This script will also print the IDs of the upstream boundary edges, which you will need for setting boundary conditions.

## Configuration

To use the 2D model, define a `HydraulicModel2D` component in your `config.yaml`.

### Example Configuration:
```yaml
components:
  - name: "Channel2D"
    type: HydraulicModel2D
    parameters:
      # Path to the mesh file, relative to the config file
      mesh_file: "channel_mesh.json"

      # Define the boundary conditions for the mesh
      boundary_conditions:
        - type: "flow"
          # A list of boundary edge IDs to apply this condition to
          edge_ids: [1, 12, 68, 172]

# Define the inflow for the 'flow' boundary
global_inputs:
  - target_component: "Channel2D"
    inputs:
      # The component name is used as the key for its primary inflow
      Channel2D:
        value: 10.0 # A constant inflow of 10 m^3/s
```

### Boundary Conditions

Boundary conditions are defined as a list under the `boundary_conditions` parameter. Each item in the list specifies a `type` and the `edge_ids` it applies to.

- **`wall` (Default):** Any boundary edge not assigned a type will default to a solid, reflective wall with zero flow across it.
- **`flow`:** This type is used to specify an inflow or outflow. The flow value itself is provided via the `global_inputs` section, where the input key matches the component's `name`. A positive value represents inflow, and a negative value represents outflow.

## Complete Example

For a complete, runnable demonstration, please see the example located in the `examples/2d_model_example/` directory. It includes a mesh file, a configuration file, and a run script that executes a simulation and plots a 2D map of the final water depth.
