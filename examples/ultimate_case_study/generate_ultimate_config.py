import yaml
import numpy as np

def generate_config():
    """Generates the YAML configuration for the ultimate case study."""

    config = {
        "simulation_parameters": {
            "dt_seconds": 3600,
            "num_steps": 240 # 10 days
        },
        "components": [],
        "network": []
    }

    # --- 1. Define Hydrological Components (50 Sub-basins) ---
    runoff_models = {
        "group1": {"type": "SCSCurveNumberModule", "params": {"CN": 75}},
        "group2": {"type": "XinanjiangRunoffModule", "params": {'K': 0.5, 'B': 0.25, 'IM': 0.05, 'UM': 10.0, 'LM': 75.0, 'DM': 90.0, 'C': 0.1, 'SM': 50.0, 'EX': 1.25, 'KI': 0.35, 'KG': 0.35}},
        "group3": {"type": "HymodRunoffModule", "params": {'cmax': 250.0, 'bexp': 1.0, 'alpha': 0.5, 'ks': 0.05, 'kq': 0.5}},
        "group4": {"type": "SCSCurveNumberModule", "params": {"CN": 65}},
        "group5": {"type": "XinanjiangRunoffModule", "params": {'K': 0.6, 'B': 0.3, 'IM': 0.02, 'UM': 15.0, 'LM': 80.0, 'DM': 100.0, 'C': 0.15, 'SM': 60.0, 'EX': 1.3, 'KI': 0.4, 'KG': 0.4}}
    }

    group_junctions = ["J_SCS", "J_XAJ", "J_HYMOD", "J_SCS_2", "J_XAJ_2"]

    for i in range(5):
        group_name = f"group{i+1}"
        junction_name = group_junctions[i]
        config["components"].append({"name": junction_name, "type": "Junction"})

        for j in range(10):
            sb_num = i * 10 + j + 1
            sb_name = f"SB{sb_num}"

            runoff_module_info = runoff_models[group_name]
            runoff_module_config = {
                "type": runoff_module_info["type"],
                "parameters": runoff_module_info["params"]
            }

            sb_config = {
                "name": sb_name,
                "type": "HydrologicalModel",
                "parameters": {
                    "runoff_module": runoff_module_config
                }
            }
            # Add routing module only if the runoff module is not self-routing (like HYMOD)
            if runoff_module_config["type"] != "HymodRunoffModule":
                sb_config["parameters"]["routing_module"] = {
                    "type": "MuskingumRouting",
                    "parameters": {"K": np.random.uniform(8, 15), "x": np.random.uniform(0.1, 0.3)}
                }

            config["components"].append(sb_config)
            config["network"].append({"from": sb_name, "to": junction_name})

    # --- 2. Define Dendritic Hydraulic Network ---
    dendritic_reaches = ["River1", "River2", "River_Trunk", "River3", "River_Final_Dendritic"]
    for reach_name in dendritic_reaches:
        config["components"].append({
            "name": reach_name,
            "type": "HydraulicModel",
            "parameters": {
                "downstream_level": 10.0, # Placeholder
                "dt": 3600,
                "reach": {
                    "type": "RiverReach",
                    "parameters": {
                        "num_nodes": 11, "length": 5000, "slope": 0.001, "manning_n": 0.03,
                        "cross_sections": [{"type": "RectangularCrossSection", "parameters": {"width": 20}}]
                    }
                }
            }
        })

    dendritic_junctions = ["J_Main_1", "J_Main_2"]
    for j_name in dendritic_junctions:
        config["components"].append({"name": j_name, "type": "Junction"})

    config["network"].extend([
        {"from": "J_SCS", "to": "River1"}, {"from": "J_XAJ", "to": "River1"},
        {"from": "J_HYMOD", "to": "River2"},
        {"from": "River1", "to": "J_Main_1"}, {"from": "River2", "to": "J_Main_1"},
        {"from": "J_Main_1", "to": "River_Trunk"},
        {"from": "J_SCS_2", "to": "River3"}, {"from": "J_XAJ_2", "to": "River3"},
        {"from": "River3", "to": "J_Main_2"}, {"from": "River_Trunk", "to": "J_Main_2"},
        {"from": "J_Main_2", "to": "River_Final_Dendritic"}
    ])

    # --- 3. Define Looped Hydraulic Network ---
    loop_reaches = ["Loop_A", "Loop_B", "Recirculation_Reach", "Final_Outflow_Component"]
    for reach_name in loop_reaches:
        config["components"].append({
            "name": reach_name, "type": "HydraulicModel",
            "parameters": {
                "downstream_level": 5.0, # Placeholder
                "dt": 3600,
                "reach": {
                    "type": "RiverReach",
                    "parameters": {
                        "num_nodes": 11, "length": 3000, "slope": 0.0005, "manning_n": 0.035,
                        "cross_sections": [{"type": "RectangularCrossSection", "parameters": {"width": 25}}]
                    }
                }
            }
        })

    loop_junctions = ["J_Loop_Split", "J_Loop_Merge"]
    for j_name in loop_junctions:
        config["components"].append({"name": j_name, "type": "Junction"})

    config["network"].extend([
        # Main flow into the loop
        {"from": "River_Final_Dendritic", "to": "J_Loop_Split"},
        # The parallel branches
        {"from": "J_Loop_Split", "to": "Loop_A"},
        {"from": "J_Loop_Split", "to": "Loop_B"},
        {"from": "Loop_A", "to": "J_Loop_Merge"},
        {"from": "Loop_B", "to": "J_Loop_Merge"},
        # The feedback connection that creates the cycle
        {"from": "J_Loop_Merge", "to": "Recirculation_Reach"},
        {"from": "Recirculation_Reach", "to": "J_Loop_Split"},
        # The final outflow from the system
        {"from": "J_Loop_Merge", "to": "Final_Outflow_Component"}
    ])

    # --- 4. Define Global Inputs ---
    config["global_inputs"] = {
        "rainfall": {"file": "rainfall.csv", "column_index": 1},
        "pet": {"file": "pet.csv", "column_index": 1}
    }

    # --- 5. Write to file ---
    with open('config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print("Successfully generated config.yaml")

if __name__ == "__main__":
    generate_config()
