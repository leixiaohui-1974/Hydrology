# Advanced Configuration Topics

This document covers advanced configuration options for more complex or customized use cases.

## Flexible Data-to-Component Mapping

By default, the framework maps data from the `data_registry` to model components by matching data source names or column names with component names. For example, a data source named `my_component` or a column named `my_component` will be automatically passed as input to the component named `my_component`.

In some cases, your data columns may have names that do not match your component names (e.g., legacy data, shapefile attributes). To handle this without renaming your data, you can use the `mapping` keyword.

The `mapping` keyword is an optional dictionary that can be added to any data source defined in the `global_inputs` section of your `config.yaml`. It provides an explicit link between a column name in your data and the name of a model component.

### How to Use

In your `global_inputs` configuration, add a `mapping` dictionary where the keys are the column names from your data file and the values are the names of the target components.

```yaml
# Define a component with a name that is different from the data column
components:
  - name: "my_model_A"
    type: HydrologicalModel
    # ... parameters ...

global_inputs:
  some_input_data:
    file: "path/to/your/data.csv"

    # Use the 'mapping' keyword to connect the data to the component
    mapping:
      # This maps the column "DATA_COLUMN_1" from data.csv
      # to the component named "my_model_A".
      "DATA_COLUMN_1": "my_model_A"
```

### Details
- When a `mapping` is provided for a data source, it takes precedence over the default name-matching behavior for that source.
- If a column or component name in the mapping is not found, a warning will be printed, but the process will continue.
- This feature provides significant flexibility for integrating data from various sources without needing to modify the source files.

### Example
For a complete, runnable demonstration of this feature, please see the example located in the `examples/flexible_mapping_example/` directory.
