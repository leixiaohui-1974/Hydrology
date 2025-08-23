# Real-Twin Framework for Smart Hydrological Forecasting

This document describes the "Real-Twin" framework, a system designed to perform real-time diagnostics on input data and produce more reliable flood forecasts.

## Core Concepts

The framework is built on three main components:

1.  **"Ground Truth" Model**: A simulation that represents the "perfect" reality of a watershed. It's used as a benchmark and to generate data for testing.
2.  **Virtual Sensor Network**: A set of simulated sensors (rain gauges, flow gauges) that "observe" the ground truth. These sensors can be configured to have random errors and systematic faults (e.g., getting clogged, drifting, or having outages).
3.  **"Digital Twin" Model with Diagnostic Engine**: This is the operational forecasting system.
    *   The **Digital Twin Model** is a hydrological model that runs using only the sparse and potentially faulty data from the virtual sensor network.
    *   The **Online Diagnostic Engine** runs alongside the twin model. It continuously analyzes the incoming sensor data, cross-validates it, and assesses the "health" of each sensor.

## Key Feature: The Feedback Loop

The most important feature of this framework is the real-time feedback loop:

1.  The Diagnostic Engine identifies a potential fault in a sensor (e.g., a rain gauge reporting no rain while a downstream flow gauge shows high flow).
2.  The engine lowers the "health score" of the suspect sensor.
3.  The system detects the low health score and triggers a **data correction** mechanism.
4.  The faulty sensor's data is replaced with an estimated value (e.g., interpolated from healthy neighbors).
5.  The Digital Twin Model uses this corrected data to run its simulation, avoiding the large errors that would have been caused by the faulty data.
6.  The system outputs not only the forecast but also a **Reliability Index**, which quantifies the confidence in the current forecast based on the health of the input data.

## How to Run the Example

An end-to-end example of this framework is provided in the `examples/real_twin_framework` directory.

### Step 1: Generate the Data

First, run the data pipeline script. This script performs two key functions:
- It generates a synthetic "ground truth" hydrograph.
- It runs the virtual sensor network to produce the `twin_rainfall.csv` and `twin_flow.csv` files, which represent the imperfect data available to the forecast model. A fault is intentionally introduced into the `RG2` rain gauge halfway through the simulation.

```bash
python3 real_twin/data_pipeline.py
```

### Step 2: Run the Real-Twin Simulation

Next, run the main simulation script. This script initializes the Digital Twin model and the Diagnostic Engine and runs them together in a feedback loop.

```bash
python3 examples/real_twin_framework/run_real_twin_simulation.py
```

### Step 3: Analyze the Results

The script will produce a `final_results.csv` file. You can inspect this file to see the framework in action. Key columns to look at are:
- `health_RG2`: You will see this value drop from 100 to 0 after the fault is detected.
- `reliability_index`: You will see this index drop as the sensor's health degrades.
- `raw_RG2` vs. `corrected_RG2`: You can compare the original faulty data with the corrected data that was actually used by the model.
- `sim_Catchment2`: You can see how the simulated flow from Catchment 2 behaves. It will be based on the corrected rainfall data, preventing a large drop in the simulated flow that would have otherwise occurred.
