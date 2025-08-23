# 2D Solver: Numerical Instability Issues

This document outlines the current numerical instability problems observed in the 2D hydraulic solver, my attempts to diagnose and fix them, and my current hypotheses about the root cause.

## Problem Description

The 2D solver exhibits numerical instability, leading to non-physical oscillations and eventual crashes, particularly in simulations with:

*   **High velocity gradients:** The instability is most pronounced in areas where the flow velocity changes rapidly, such as near sharp corners or obstructions.
*   **Complex bathymetry:** Models with highly variable bed elevation are more prone to instability.
*   **Small time steps:** While counterintuitive, reducing the time step does not always resolve the issue and can sometimes exacerbate it.

## Troubleshooting Attempts

I have attempted the following to resolve the instability:

1.  **Time Step Reduction:** I have tried using smaller time steps, but this has not been effective.
2.  **Artificial Viscosity:** I have experimented with adding artificial viscosity to the momentum equations. This helps to damp the oscillations but also introduces excessive diffusion, which is not ideal.
3.  **Solver Scheme:** I have reviewed the implementation of the finite volume solver, but I have not yet been able to identify any obvious errors.

## Hypothesis

My current hypothesis is that the issue stems from the flux calculation at cell interfaces, especially in the presence of strong shocks or high Froude numbers. The current implementation may not be robust enough to handle these conditions, leading to the observed instabilities.

Further investigation is required to confirm this hypothesis and to develop a more robust and accurate solver.
