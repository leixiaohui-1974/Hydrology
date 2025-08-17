import numpy as np
import matplotlib.pyplot as plt
from hydro_model.routing import UnitHydrographRouting

def main():
    print("--- Running Unit Hydrograph Routing Example ---")

    # 1. Define a sample Unit Hydrograph (ordinates must sum to 1.0)
    # This represents the response to 1 unit of rain over 1 time step.
    uh_ordinates = np.array([0.1, 0.3, 0.4, 0.15, 0.05])

    # 2. Create routing module instance
    uh_router = UnitHydrographRouting(uh_ordinates=uh_ordinates)

    # 3. Create a sample effective rainfall series (e.g., from a runoff module)
    effective_rainfall = np.array([10, 25, 5, 0, 0, 0, 0, 0, 0, 0])
    timesteps = np.arange(len(effective_rainfall))

    print(f"Input Effective Rainfall (mm): {effective_rainfall}")

    # 4. Run the routing simulation
    outflow_hydrograph = []
    for rain_val in effective_rainfall:
        outflow_val = uh_router.run(rain_val)
        outflow_hydrograph.append(outflow_val)

    outflow_hydrograph = np.array(outflow_hydrograph)

    print(f"Output Direct Runoff Hydrograph (mm): {np.round(outflow_hydrograph, 2)}")

    # 5. Plot the results for visual verification
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Plot rainfall as bars
    ax1.bar(timesteps, effective_rainfall, width=0.8, color='c', alpha=0.6, label='Effective Rainfall')
    ax1.set_xlabel('Time Step (days)')
    ax1.set_ylabel('Rainfall (mm)', color='c')
    ax1.tick_params(axis='y', labelcolor='c')
    ax1.invert_yaxis()

    # Plot hydrograph on a second y-axis
    ax2 = ax1.twinx()
    ax2.plot(timesteps, outflow_hydrograph, 'r-o', label='Direct Runoff Hydrograph')
    ax2.set_ylabel('Flow (mm depth equivalent)', color='r')
    ax2.tick_params(axis='y', labelcolor='r')

    plt.title('Unit Hydrograph Routing Example')
    fig.tight_layout()

    output_path = 'results/uh_example_plot.png'
    plt.savefig(output_path)
    print(f"\nRouting plot saved to {output_path}")
    print("Example finished successfully.")

if __name__ == "__main__":
    main()
