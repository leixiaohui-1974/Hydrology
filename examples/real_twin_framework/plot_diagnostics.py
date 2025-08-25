import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

def main():
    """
    Reads the final simulation results and creates a diagnostic plot.
    """
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


    try:
        df = pd.read_csv('examples/real_twin_framework/final_results.csv', index_col='time_step')
    except FileNotFoundError:
        print("Error: final_results.csv not found.")
        print("Please run run_real_twin_simulation.py first.")
        return

    print("Generating diagnostic plot...")

    # Create a figure with a complex grid layout
    fig = plt.figure(figsize=(15, 12))
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 2])

    # --- Subplot 1: Simulated Flow ---
    ax1 = plt.subplot(gs[0])
    ax1.plot(df.index, df['sim_Catchment1'], label='Simulated Flow (Outlet)', color='b', linewidth=2)
    ax1.set_ylabel('Flow (m³/s)')
    ax1.set_title('Real-Twin Framework: Diagnostic and Correction Results')
    ax1.legend()
    ax1.grid(True, linestyle='--', alpha=0.6)

    # --- Subplot 2: Reliability Index ---
    ax2 = plt.subplot(gs[1], sharex=ax1)
    ax2.plot(df.index, df['reliability_index'], label='Forecast Reliability Index', color='g')
    ax2.set_ylabel('Reliability (%)')
    ax2.set_ylim(0, 110)
    ax2.legend()
    ax2.grid(True, linestyle='--', alpha=0.6)

    # --- Subplot 3: Sensor Health ---
    ax3 = plt.subplot(gs[2], sharex=ax1)
    ax3.plot(df.index, df['health_RG1'], label='Health RG1', linestyle='-')
    ax3.plot(df.index, df['health_RG2'], label='Health RG2', linestyle='--')
    ax3.plot(df.index, df['health_RG3'], label='Health RG3', linestyle=':')
    ax3.set_ylabel('Health Score')
    ax3.set_ylim(0, 110)
    ax3.legend()
    ax3.grid(True, linestyle='--', alpha=0.6)

    # --- Subplot 4: Raw vs Corrected Rainfall ---
    ax4 = plt.subplot(gs[3], sharex=ax1)
    ax4.plot(df.index, df['raw_RG2'], 'r-o', label='Raw RG2 (Faulty)', markersize=4)
    ax4.plot(df.index, df['corrected_RG2'], 'g-o', label='Corrected RG2', markersize=4)
    ax4.set_xlabel('Time Step')
    ax4.set_ylabel('Rainfall (as flow rate)')
    ax4.legend()
    ax4.grid(True, linestyle='--', alpha=0.6)

    # Improve layout and save the figure
    plt.tight_layout()
    output_path = 'examples/real_twin_framework/diagnostic_plot.png'
    plt.savefig(output_path)

    print(f"Diagnostic plot saved to {output_path}")

if __name__ == "__main__":
    main()
