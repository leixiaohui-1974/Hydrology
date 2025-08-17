import numpy as np
import matplotlib.pyplot as plt
from hydro_model.routing import MuskingumCungeRouting

def main():
    print("--- Running Muskingum-Cunge Routing Example ---")

    # 1. Define physical channel parameters
    params = {
        'length': 5000,    # 5 km reach length (m)
        'slope': 0.0002,   # (m/m)
        'manning_n': 0.03, # Roughness
        'width': 50.0,     # Channel width (m)
        'dt': 1.0          # Time step in days
    }

    # 2. Create routing module instance
    mc_router = MuskingumCungeRouting(**params)

    # 3. Create a sample inflow hydrograph
    inflow_hydrograph = np.array([0, 10, 20, 40, 60, 45, 30, 20, 10, 5, 2, 1, 0, 0, 0], dtype=float)
    timesteps = np.arange(len(inflow_hydrograph))

    print(f"Input Inflow Hydrograph (m3/s): {inflow_hydrograph}")

    # 4. Run the routing simulation
    outflow_hydrograph = []
    water_depth_series = []
    for inflow_val in inflow_hydrograph:
        outflow_val = mc_router.run(inflow_val)
        outflow_hydrograph.append(outflow_val)
        # Access the calculated water depth from the previous step
        water_depth_series.append(mc_router.y_prev)

    outflow_hydrograph = np.array(outflow_hydrograph)
    water_depth_series = np.array(water_depth_series)

    print(f"Output Outflow Hydrograph (m3/s): {np.round(outflow_hydrograph, 2)}")
    print(f"Simulated Water Depth (m): {np.round(water_depth_series, 2)}")

    # 5. Plot the results
    # Plot 1: Flow routing
    plt.figure(figsize=(12, 10))

    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(timesteps, inflow_hydrograph, 'b-o', label='Inflow')
    ax1.plot(timesteps, outflow_hydrograph, 'r--s', label='Outflow (Muskingum-Cunge)')
    ax1.set_title('Flow Routing Comparison')
    ax1.set_xlabel('Time Step (days)')
    ax1.set_ylabel('Flow (m³/s)')
    ax1.legend()
    ax1.grid(True)

    # Plot 2: Water level simulation
    ax2 = plt.subplot(2, 1, 2)
    ax2.plot(timesteps, water_depth_series, 'g-^', label='Average Water Depth')
    ax2.set_title('Simulated In-stream Water Depth')
    ax2.set_xlabel('Time Step (days)')
    ax2.set_ylabel('Water Depth (m)')
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    output_path = 'results/muskingum_cunge_example_plot.png'
    plt.savefig(output_path)
    print(f"\nRouting and water level plot saved to {output_path}")
    print("Example finished successfully.")

if __name__ == "__main__":
    main()
