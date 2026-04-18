"""
Module for generating simulation configurations from GUI data.
"""

def generate_config_from_gui_data(gui_data):
    """
    Translates the flat data structure from the GUI into a nested dictionary
    that conforms to the model's YAML configuration format.

    This is a critical translation step. The GUI represents the model as a
    graph of nodes and connections, while the simulation engine expects a
    structured configuration file.

    Args:
        gui_data (dict): The entire state of the frontend application.

    Returns:
        dict: A dictionary structured like the required YAML config file.
    """
    print("DEBUG: Generating config from GUI data:", gui_data)

    config = {
        "simulation_parameters": gui_data.get("sim_params", {}),
        "components": [],
        "network": [],
        "global_inputs": gui_data.get("global_inputs", {})
    }

    # This function needs to be more sophisticated to handle nested components
    # like structures within a HydraulicModel.

    # First pass: create all top-level components
    component_map = {} # temp map from name to component config dict
    structures_to_place = []

    for node_id, node_data in gui_data.get("nodes", {}).items():
        # A simple convention: structures are not top-level components
        is_structure = node_data["type"] in ["Gate", "Pump", "Weir"]

        if not is_structure:
            # Make a copy of params to avoid modifying the original GUI data
            params = node_data["params"].copy()

            # For 2D models, check if a mesh has been generated dynamically
            if node_data["type"] == "HydraulicModel2D":
                if params.get("generated_mesh_file"):
                    # Use the generated mesh file for the simulation
                    params["mesh_file"] = params["generated_mesh_file"]
                else:
                    # This case should be handled by the UI, but as a fallback:
                    print("Warning: HydraulicModel2D is missing a generated mesh file. Simulation may fail.")

            component_config = {
                "name": node_data["name"],
                "type": node_data["type"],
                "parameters": params
            }
            # Ensure structures list exists for hydraulic models
            if node_data["type"] == "HydraulicModel":
                component_config["parameters"]["structures"] = []

            config["components"].append(component_config)
            component_map[node_data["name"]] = component_config
        else:
            structures_to_place.append(node_data)

    # Second pass: place structures into their parents
    for struct_data in structures_to_place:
        parent_name = struct_data["params"].pop("parent_reach", None)
        if parent_name and parent_name in component_map:
            # This is a sub-component, add it to the parent's parameters
            parent_component_config = component_map[parent_name]
            structure_config = {
                "name": struct_data["name"],
                "type": struct_data["type"],
                "parameters": struct_data["params"]
            }
            parent_component_config["parameters"]["structures"].append(structure_config)
        else:
            # It's a top-level component after all, or parent not found
             print(f"Warning: Could not place structure '{struct_data['name']}'. Parent reach '{parent_name}' not found.")


    # Format network connections
    for conn in gui_data.get("connections", []):
        from_name = gui_data["nodes"][conn["from"]]["name"]
        to_name = gui_data["nodes"][conn["to"]]["name"]
        config["network"].append({"from": from_name, "to": to_name})

    # Format data source configurations and build global_inputs mapping
    config["data_sources"] = gui_data.get("data_sources_store", {})
    config["global_inputs"] = []

    for node_id, node_data in gui_data.get("nodes", {}).items():
        if node_data["type"] == "HydrologicalModel":
            rainfall_source = node_data["params"].get("rainfall_source")
            if rainfall_source:
                # This assumes rainfall is a single column file for now
                # A more robust solution would also let user select the column
                input_map = {
                    "target_component": node_data["name"],
                    "inputs": {
                        "rainfall": {
                            "from_source": rainfall_source,
                            "from_column": config["data_sources"][rainfall_source].get("columns", ["col1"])[0] # Placeholder for column name
                        }
                    }
                }
                config["global_inputs"].append(input_map)

    # This is a simplified config generation. A full implementation would
    # handle all data source types and preprocessing steps dynamically.
    print("DEBUG: Generated config dict:", config)
    return config
