"""
Main Python script for the Eel-based GUI.
"""
import eel

# Initialize Eel, specifying the web folder
eel.init('web')

import yaml

@eel.expose  # Expose this function to Javascript
def save_config_to_yaml(data):
    """Receives data from the JS front-end and saves it as a YAML file."""
    print("Received data from GUI to save.")

    # The data from JS is a dict with 'nodes' and 'connections'
    nodes_data = data['nodes']
    connections_data = data['connections']

    # Transform the data into the format expected by our config parser
    config = {
        'simulation_parameters': {
            'dt_seconds': 60,
            'num_steps': 120
        },
        'components': [],
        'network': []
    }

    # Re-map node IDs (like 'node-1') to the user-defined component names
    id_to_name_map = {node_id: node_info['name'] for node_id, node_info in nodes_data.items()}

    for node_id, node_info in nodes_data.items():
        # This is a simplified transformation. A real one would be more robust.
        component_def = {
            'name': node_info['name'],
            'type': node_info['type'],
            'parameters': node_info['params']
        }
        config['components'].append(component_def)

    for connection in connections_data:
        config['network'].append({
            'from': id_to_name_map[connection['from']],
            'to': id_to_name_map[connection['to']]
        })

    output_filename = 'gui_output_config.yaml'
    try:
        with open(output_filename, 'w') as f:
            yaml.dump(config, f, sort_keys=False, indent=2)
        print(f"Successfully saved configuration to {output_filename}")
        return f"Saved to {output_filename}"
    except Exception as e:
        print(f"Error saving YAML file: {e}")
        return f"Error: {e}"

def main():
    """
    Starts the Eel application.
    """
    print("Starting GUI...")
    # Start the application. `size` is a suggestion.
    eel.start('index.html', size=(1280, 800))
    print("GUI closed.")

if __name__ == "__main__":
    main()
