import pandas as pd
import matplotlib.pyplot as plt

def plot_flow_comparison():
    """Plots the comparison of observed, open-loop, and assimilated flows."""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


    df = pd.read_csv('results/enkf_flow_results.csv', index_col='date', parse_dates=True)

    plt.figure(figsize=(15, 7))
    plt.plot(df.index, df['observed_flow'], 'k.', label='Observed Flow')
    plt.plot(df.index, df['open_loop_flow'], 'r--', label='Open-Loop (No Assimilation)')
    plt.plot(df.index, df['assimilated_flow'], 'b-', label='EnKF Assimilated Flow')

    plt.title('Comparison of Hydrological Model Flows')
    plt.xlabel('Date')
    plt.ylabel('Flow (m³/s)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    output_path = 'results/enkf_flow_comparison.png'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"Flow comparison plot saved to {output_path}")
    plt.close()

def plot_parameter_evolution():
    """Plots the evolution of the estimated model parameters over time."""
    df = pd.read_csv('results/enkf_parameter_evolution.csv', index_col='date', parse_dates=True)

    # We are interested in the parameters, not the states S and Q_s for this plot
    params_to_plot = ['S_max', 'k_q', 'k_s', 'c_loss']

    fig, axes = plt.subplots(nrows=len(params_to_plot), ncols=1, figsize=(12, 10), sharex=True)
    fig.suptitle('Evolution of Model Parameters via EnKF', fontsize=16)

    for i, param in enumerate(params_to_plot):
        axes[i].plot(df.index, df[param], label=f'Estimated {param}')
        axes[i].set_ylabel(param)
        axes[i].legend(loc='upper right')
        axes[i].grid(True, linestyle='--', alpha=0.6)

    axes[-1].set_xlabel('Date')
    plt.tight_layout(rect=[0, 0, 1, 0.96]) # Adjust layout to make room for suptitle

    output_path = 'results/enkf_parameter_convergence.png'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"Parameter evolution plot saved to {output_path}")
    plt.close()

if __name__ == "__main__":
    plot_flow_comparison()
    plot_parameter_evolution()
