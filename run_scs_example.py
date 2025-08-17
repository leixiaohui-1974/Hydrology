import numpy as np
from hydro_model.model import HydrologicalModel
from hydro_model.runoff import SCSCurveNumberModule
from hydro_model.routing import SimpleRouting

def main():
    print("--- Running SCS Curve Number Model Example ---")

    # 1. Define Parameters
    # We only need CN for the runoff module, and k_q/k_s for the routing module
    params = {'CN': 85, 'k_q': 0.8, 'k_s': 0.1}

    # 2. Create model components
    scs_runoff_module = SCSCurveNumberModule(**params)
    simple_routing_module = SimpleRouting(**params)

    # 3. Compose the main hydrological model
    model = HydrologicalModel(
        runoff_module=scs_runoff_module,
        routing_module=simple_routing_module
    )

    # 4. Run simulation with sample data
    sample_rainfall = [0, 5, 10, 30, 50, 20, 10, 5, 0]
    print(f"Input Rainfall (mm): {sample_rainfall}")

    print("\n--- Simulation Results ---")
    print("Time | Rainfall | Runoff (mm)")
    print("----------------------------")

    total_runoff = 0
    for t, rain in enumerate(sample_rainfall):
        # The model's run method returns the final routed flow in mm depth equivalent
        runoff_mm = model.run(rainfall=rain, pet=0)
        total_runoff += runoff_mm
        print(f"{t:4d} | {rain:8.2f} | {runoff_mm:10.4f}")

    print("----------------------------")
    print(f"Total Runoff: {total_runoff:.4f} mm")
    print("\nExample finished successfully.")

if __name__ == "__main__":
    main()
