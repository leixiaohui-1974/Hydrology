import numpy as np
import matplotlib.pyplot as plt
import sys
import os
# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hydro_model.catchment import Catchment
from hydro_model.routing import MuskingumCungeRouting

def main():
    print("--- Running River Network Simulation Example ---")

    # 1. Create a Catchment instance
    network = Catchment()

    # 2. Add nodes
    for i in range(1, 5):
        network.add_node(f"N{i}")

    # 3. Define reach properties and add reaches
    # Using Muskingum-Cunge for all reaches
    reach1_params = {'length': 5000, 'slope': 0.0003, 'manning_n': 0.035, 'width': 30.0}
    reach2_params = {'length': 4000, 'slope': 0.0004, 'manning_n': 0.04, 'width': 25.0}
    reach3_params = {'length': 8000, 'slope': 0.0002, 'manning_n': 0.03, 'width': 50.0}

    network.add_reach("R1", "N1", "N3", MuskingumCungeRouting(**reach1_params))
    network.add_reach("R2", "N2", "N3", MuskingumCungeRouting(**reach2_params))
    network.add_reach("R3", "N3", "N4", MuskingumCungeRouting(**reach3_params))

    # 4. Define inflows
    T = 40 # Total timesteps (days)
    # Inflow for tributary 1 (Node 1)
    inflow1 = np.array([0,0,5,15,25,20,15,10,5,3,1,0,0,0,0,0,0,0,0,0] + [0]*20)
    # Inflow for tributary 2 (Node 2), slightly delayed
    inflow2 = np.array([0,0,0,0,0,3,10,20,18,15,10,8,5,3,1,0,0,0,0,0] + [0]*20)
    # Lateral inflow along the main reach (Reach 3)
    lateral_inflow3 = np.array([1,1,2,3,3,3,2,2,1,1,0,0,0,0,0,0,0,0,0,0] + [0]*20)

    headwater_inflows = {"N1": inflow1, "N2": inflow2}
    lateral_inflows = {"R3": lateral_inflow3}

    # 5. Run the simulation
    print("Running network simulation...")
    reach_q, node_q = network.run_simulation(headwater_inflows, lateral_inflows, T)
    print("Simulation complete.")

    # 6. Plot results
    plt.figure(figsize=(15, 7))
    timesteps = np.arange(T)

    plt.plot(timesteps, headwater_inflows['N1'], 'b--', label='Inflow at N1 (Tributary 1)')
    plt.plot(timesteps, headwater_inflows['N2'], 'g--', label='Inflow at N2 (Tributary 2)')
    plt.plot(timesteps, node_q['N4'], 'r-', linewidth=2, label='Outflow at N4 (Final Outlet)')

    plt.title('River Network Hydrodynamic Simulation')
    plt.xlabel('Time Step (days)')
    plt.ylabel('Flow (m³/s)')
    plt.legend()
    plt.grid(True)

    output_path = 'results/network_simulation_plot.png'
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"\nNetwork simulation plot saved to {output_path}")

if __name__ == "__main__":
    main()
