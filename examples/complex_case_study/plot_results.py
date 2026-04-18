import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import matplotlib.pyplot as plt
import os

# Create results directory if it doesn't exist
os.makedirs('results', exist_ok=True)

# Plot parameter evolution
params_df = pd.read_csv('results/complex_calibration_parameters.csv', index_col=0)
plt.figure(figsize=(12, 6))
params_df.plot()
plt.title('Parameter Evolution during Calibration')
plt.xlabel('Time Step')
plt.ylabel('Parameter Value')
plt.legend(title='Parameter')
plt.grid(True)
plt.savefig('results/parameter_evolution.png')
plt.close()

# Plot flow results
flow_df = pd.read_csv('results/complex_calibration_flows.csv', index_col=0)
plt.figure(figsize=(12, 8))
# Get zone ids from column names like 'sim_Z1', 'obs_Z1'
zone_ids = sorted(list(set([c.split('_')[1] for c in flow_df.columns])))
for i, z_id in enumerate(zone_ids):
    plt.subplot(len(zone_ids), 1, i+1)
    plt.plot(flow_df.index, flow_df[f'sim_{z_id}'], label='Simulated Flow')
    plt.plot(flow_df.index, flow_df[f'obs_{z_id}'], label='Observed Flow', linestyle='--')
    plt.title(f'Flow Comparison for Zone {z_id}')
    plt.ylabel('Flow')
    plt.legend()
    plt.grid(True)
plt.xlabel('Time Step')
plt.tight_layout()
plt.savefig('results/flow_comparison.png')
plt.close()

print("Plots saved to 'results/parameter_evolution.png' and 'results/flow_comparison.png'")
