# 1D Hydraulic Model (`preissmann_model`)

The `preissmann_model` is a powerful component for simulating 1D unsteady flow in open channels. It solves the full Saint-Venant equations using the implicit Preissmann scheme, which is robust and suitable for a wide range of subcritical flow scenarios.

## `HydraulicModel` Component

The main component for a hydraulic simulation is the `HydraulicModel`. It represents a single river reach and orchestrates the solver.

**Example Configuration:**
```yaml
components:
  - name: "MyRiver"
    type: HydraulicModel
    parameters:
      dt: 60 # Timestep in seconds
      downstream_level: 10.0 # Downstream water level boundary condition
      reach: { ... } # RiverReach definition, see below
      structures: [ ... ] # List of hydraulic structures, see below
```

## `RiverReach` Configuration

The `reach` parameter defines the physical properties of the river channel.

```yaml
      reach:
        type: RiverReach
        parameters:
          num_nodes: 10
          length: 1000 # meters
          slope: 0.001 # m/m
          manning_n: 0.03
          cross_sections:
            - type: ... # Cross-section definition, see below
```

## Cross-Section Types

The `cross_sections` parameter defines the shape of the river channel. If only one cross-section is provided, it is assumed to be uniform for the entire reach (prismatic channel).

### `RectangularCrossSection`
A simple rectangle.
```yaml
          cross_sections:
            - type: RectangularCrossSection
              parameters:
                width: 20.0 # meters
```

### `TrapezoidalCrossSection`
A trapezoidal shape, useful for engineered channels.
```yaml
          cross_sections:
            - type: TrapezoidalCrossSection
              parameters:
                bottom_width: 20.0 # meters
                side_slope: 2.0 # 2:1 (H:V) side slope
```

### `IrregularCrossSection`
Defines an arbitrary shape using a series of station-elevation points. This is ideal for natural river channels.
```yaml
          cross_sections:
            - type: IrregularCrossSection
              parameters:
                # List of (station, elevation) tuples
                points:
                  - [0, 15]
                  - [10, 10]
                  - [30, 10]
                  - [40, 15]
```

## Hydraulic Structures

Hydraulic structures like gates, pumps, or weirs can be placed at nodes within the river reach. They are defined in a list under the `structures` parameter of the `HydraulicModel`.

### `Gate`
A sluice gate structure.
```yaml
      structures:
        - name: "SluiceGate"
          type: Gate
          parameters:
            node_index: 4 # Place at the 5th node (0-indexed)
            opening_height: 1.0 # meters
            width: 20.0 # meters
            C_d: 0.6 # Discharge coefficient
```

### `Pump`
A pump with a characteristic curve.
```yaml
      structures:
        - name: "MyPump"
          type: Pump
          parameters:
            node_index: 2
            # Coefficients (a, b, c) for delta_H = a*Q^2 + b*Q + c
            curve_coeffs: [-0.001, 0.1, 5.0]
```

### `Weir`
A broad-crested weir structure.
```yaml
      structures:
        - name: "UpstreamWeir"
          type: Weir
          parameters:
            node_index: 4
            crest_elevation: 12.0 # meters
            width: 20.0 # meters
            C_d: 1.6 # Discharge coefficient
```

## Complete Example

For a complete, runnable demonstration of these features, please see the example located in the `examples/hydraulic_features_example/` directory.
