import yaml
import json
from pathlib import Path

def generate_yjdt_synthetic_graph(case_id="yjdt"):
    import re
    manifest_path = Path(__file__).resolve().parent.parent.parent / "cases" / "yjdt" / "contracts" / "case_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing YJDT contract manifest at {manifest_path}")
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    notes = data.get("notes", "")
    # Parse dam names and MW from notes: e.g. "墨脱(6GW)→多雄藏布(3.2GW)"
    pattern = r"([\u4e00-\u9fa5]+)\(([\d\.]+)GW\)"
    matches = re.findall(pattern, notes)
    
    entities = []
    edges = []
    
    if not matches:
        return {"entities": [], "edges": []}
        
    for i, (name, mw) in enumerate(matches):
        pid = f"yjdt_station_{i}"
        entities.append({
            "id": pid,
            "name": f"{name}水电站",
            "type": "turbine",
            "state": {"capacity": f"{mw} GW", "status": "active_planning"}
        })
        if i > 0:
            prev_id = f"yjdt_station_{i-1}"
            edges.append({
                "id": f"flow_{prev_id}_to_{pid}",
                "source": prev_id,
                "target": pid,
                "label": "深埋隧洞引水"
            })
            
    return {"entities": entities, "edges": edges}


def parse_pipedream_yaml_to_mcp_graph(yaml_path: str):
    """
    Reads a pipedream `.yaml` configuration (e.g., yinchuo.yaml) and 
    extrapolates its network definitions into a standard HydroMind ReactFlow DTO
    (Entities and Edges matrix).
    """
    path = Path(yaml_path)
    case_id = path.stem
    
    # Special handling for YJDT which operates on contract manifest level initially
    if "yjdt" in str(path) or not path.exists() and "yjdt" in case_id:
        return generate_yjdt_synthetic_graph()
        
    if not path.exists():
        raise FileNotFoundError(f"Missing Pipedream config: {path}")
        
    # Attempt to load deep algorithmic simulation parameters from pipeline summary
    summary_path = path.parent.parent.parent.parent / "research" / "e2e_reports" / case_id / f"{case_id}_pipeline_summary.json"
    algo_metadata = {}
    if summary_path.exists():
        with open(summary_path, 'r', encoding='utf-8') as sf:
            try:
                pipeline_data = json.load(sf)
                # Extract cutting-edge algorithmic data
                algo_metadata = {
                    "mpc_controller": pipeline_data.get("mpc_controller", {}),
                    "kalman_filter": pipeline_data.get("kalman_filter", {}),
                    "identification_fopdt": pipeline_data.get("identification", {}),
                    "odd_validation_scenarios": [s.get("name") for s in pipeline_data.get("odd_validation", {}).get("scenarios", [])]
                }
            except Exception:
                pass
                
        # Inject dynamic NPZ time-series
        try:
            import numpy as np
            npz_path = summary_path.parent / "sim_step_response.npz"
            if not npz_path.exists():
                npz_path = summary_path.parent / "sim_data_72h.npz"
                
            if npz_path.exists():
                data = np.load(npz_path)
                # Downsample to max 20 points for UI Sparklines
                times_arr = data['times'] if 'times' in data else []
                if len(times_arr) > 0:
                    step = max(1, len(times_arr) // 20)
                    h_series = data.get('H_j_series', [])
                    if len(h_series) > 0:
                        # Extract first node's history
                        algo_metadata["timeseries_h"] = [float(x) for x in h_series[::step, 0]]
                    q_series = data.get('Q_o_series', [])
                    if len(q_series) > 0:
                        # Extract first gate's flow history
                        algo_metadata["timeseries_q"] = [float(x) for x in q_series[::step, 0]]
        except Exception as e:
            pass
            
        
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    case_id = config.get("meta", {}).get("id", "unknown_case")
    network = config.get("model", {}).get("network", {})
    
    n_nodes = network.get("n_nodes", 0)
    # Different link types representing structural pipes/assets
    n_links = network.get("n_links", 0)
    n_orifices = network.get("n_orifices", 0)
    n_pumps = network.get("n_pumps", 0)
    n_weirs = network.get("n_weirs", 0)
    n_siphons = network.get("n_siphons", 0)
    
    entities = []
    edges = []
    
    # Generate Synthetic Pipedream Physical Logical Nodes
    for i in range(n_nodes):
        entities.append({
            "id": f"{case_id}_node_{i}",
            "name": f"管网节点 {i}",
            "type": "channel",  # Base representation
            "state": {
                "head_m": 0.0,
                "demand": 0.0,
                "status": "active"
            }
        })
        
    # Generate logical DAG edges based on simplified n_link linear arrangement 
    # (assuming mainline serial topology if proper link matrix is absent in the YAML root)
    current_node_idx = 0
    total_structures = n_links + n_orifices + n_pumps + n_weirs + n_siphons
    
    structure_components = [
        ("pump", "valve_pump", n_pumps),
        ("orifice", "valve_pump", n_orifices),
        ("weir", "valve_pump", n_weirs),
        ("siphon", "channel", n_siphons),
        ("reach", "channel", n_links)
    ]
    
    struct_id_counter = 0
    for st_name, st_type, count in structure_components:
        for _ in range(count):
            if current_node_idx >= n_nodes - 1:
                break
            
            src = f"{case_id}_node_{current_node_idx}"
            tgt = f"{case_id}_node_{current_node_idx+1}"
            
            # The structure itself becomes an Entity (e.g., Pump, Orifice) mounted between two nodes
            struct_id = f"{case_id}_{st_name}_{struct_id_counter}"
            entities.append({
                "id": struct_id,
                "name": f"{st_name.upper()} 架构实体",
                "type": st_type,
                "state": {"flow": 0.0, "status": "functional"}
            })
            
            # Create two links: Node -> Structure -> Node
            edges.append({"id": f"e_in_{struct_id}", "source": src, "target": struct_id, "label": "inflow"})
            edges.append({"id": f"e_out_{struct_id}", "source": struct_id, "target": tgt, "label": "outflow"})
            
            current_node_idx += 1
            struct_id_counter += 1
            
    # Inject Model Predictive Control (MPC) and deep algo metrics into the first primary control structure found
    if algo_metadata and entities:
        for ent in entities:
            if ent["type"] == "valve_pump" or ent["type"] == "turbine":
                ent["state"]["algorithmic_parameters"] = algo_metadata
                break
                
    return {
        "entities": entities,
        "edges": edges,
        "algo_metadata": algo_metadata
    }

if __name__ == "__main__":
    import sys
    test_file = "../../pipedream-hydrology-integration-lab/hydromind_control_server/configs/cases/yinchuo.yaml"
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        
    try:
        graph = parse_pipedream_yaml_to_mcp_graph(test_file)
        print(f"✅ Adapter Loaded Config: {test_file}")
        print(f"🏭 Generated {len(graph['entities'])} Physical Entities")
        print(f"🔗 Generated {len(graph['edges'])} Logical Edges")
        # print(json.dumps(graph, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error: {e}")
