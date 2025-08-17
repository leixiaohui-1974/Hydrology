import numpy as np
import matplotlib.pyplot as plt
from hydro_model.routing import MuskingumRouting

def main():
    print("--- Running Muskingum Routing Example ---")

    # 1. Define Parameters
    # K and x are the core Muskingum parameters
    params = {'K': 2.0, 'x': 0.2} # K=2 days, x=0.2

    # 2. Create routing module instance
    muskingum_router = MuskingumRouting(**params)

    # 3. Create a sample inflow hydrograph (e.g., triangular shape)
    inflow_hydrograph = np.array([0, 10, 20, 40, 60, 45, 30, 20, 10, 5, 2, 1, 0, 0, 0])
    timesteps = np.arange(len(inflow_hydrograph))

    print(f"Input Inflow Hydrograph: {inflow_hydrograph}")

    # 4. Run the routing simulation
    outflow_hydrograph = []
    for inflow_val in inflow_hydrograph:
        outflow_val = muskingum_router.run(inflow_val)
        outflow_hydrograph.append(outflow_val)

    outflow_hydrograph = np.array(outflow_hydrograph)

    print(f"Output Outflow Hydrograph: {np.round(outflow_hydrograph, 2)}")

    # 5. Plot the results for visual verification
    plt.figure(figsize=(10, 6))
    plt.plot(timesteps, inflow_hydrograph, 'b-o', label='Inflow Hydrograph')
    plt.plot(timesteps, outflow_hydrograph, 'r--s', label='Outflow Hydrograph (Routed)')
    plt.title('Muskingum Routing Example')
    plt.xlabel('Time Step (days)')
    plt.ylabel('Flow (m³/s)')
    plt.legend()
    plt.grid(True)

    output_path = 'results/muskingum_example_plot.png'
    plt.savefig(output_path)
    print(f"\nRouting plot saved to {output_path}")
    print("Example finished successfully.")

if __name__ == "__main__":
    main()
