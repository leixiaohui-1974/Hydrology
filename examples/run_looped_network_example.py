import numpy as np
import matplotlib.pyplot as plt
import sys
import os
# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hydro_model.catchment import Catchment
from hydro_model.routing import MuskingumCungeRouting

def main():
    print("--- Running Looped River Network Simulation Example ---")

    network = Catchment()

    # 1. Define network topology (a diamond-shaped loop)
    nodes = [f"N{i}" for i in range(1, 7)]
    for node_id in nodes:
        network.add_node(node_id)

    # Define physical properties for each reach
    # Let's make the two branches of the loop different
    reach_params = {
        "R1": {'length': 2000, 'slope': 0.0005, 'manning_n': 0.04, 'width': 30.0},
        "R2": {'length': 4000, 'slope': 0.0003, 'manning_n': 0.03, 'width': 20.0}, # West branch
        "R3": {'length': 4000, 'slope': 0.0003, 'manning_n': 0.05, 'width': 25.0}, # East branch (rougher)
        "R4": {'length': 1000, 'slope': 0.0003, 'manning_n': 0.03, 'width': 20.0},
        "R5": {'length': 1000, 'slope': 0.0003, 'manning_n': 0.05, 'width': 25.0},
        "R6": {'length': 3000, 'slope': 0.0002, 'manning_n': 0.03, 'width': 40.0}
    }

    # Add reaches to form the diamond loop
    network.add_reach("R1", "N1", "N2", MuskingumCungeRouting(**reach_params["R1"]))
    network.add_reach("R2", "N2", "N3", MuskingumCungeRouting(**reach_params["R2"]))
    network.add_reach("R3", "N2", "N4", MuskingumCungeRouting(**reach_params["R3"]))
    network.add_reach("R4", "N3", "N5", MuskingumCungeRouting(**reach_params["R4"]))
    network.add_reach("R5", "N4", "N5", MuskingumCungeRouting(**reach_params["R5"]))
    network.add_reach("R6", "N5", "N6", MuskingumCungeRouting(**reach_params["R6"]))

    # 2. Define inflows
    T = 50
    inflow_hydrograph = np.array([0,0,0,10,25,50,70,60,45,30,20,15,10,5,2,1] + [0]*34)
    headwater_inflows = {"N1": inflow_hydrograph}
    lateral_inflows = {} # No lateral inflows for this example

    # 3. Run the iterative simulation
    print("Running iterative simulation for looped network...")
    reach_q, node_q = network.run_iterative_simulation(headwater_inflows, lateral_inflows, T)
    print("Simulation complete.")

    # 4. Plot results
    plt.figure(figsize=(15, 8))
    timesteps = np.arange(T)

    plt.plot(timesteps, headwater_inflows['N1'], 'k--', label='Inflow at N1')
    plt.plot(timesteps, reach_q['R2'], 'b-', label='Flow in West Branch (R2)')
    plt.plot(timesteps, reach_q['R3'], 'g-', label='Flow in East Branch (R3)')
    plt.plot(timesteps, node_q['N6'], 'r-', linewidth=2, label='Outflow at N6 (Final Outlet)')

    plt.title('Simulation of a Looped River Network')
    plt.xlabel('Time Step (days)')
    plt.ylabel('Flow (m³/s)')
    plt.legend()
    plt.grid(True)

    output_path = 'results/looped_network_plot.png'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"\nLooped network simulation plot saved to {output_path}")

if __name__ == "__main__":
    main()
