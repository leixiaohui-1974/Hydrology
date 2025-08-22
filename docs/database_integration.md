# Database Integration (PostGIS)

For larger and more professional projects, managing spatial and time series data in a database is often preferable to using local files. This framework supports loading data directly from a PostGIS database.

## Feature Overview

- **Direct Loading:** Data sources can be defined as SQL queries that are executed against a specified PostGIS database.
- **GeoPandas Integration:** The framework uses `GeoPandas` and `GeoAlchemy2` to automatically read spatial data (i.e., columns of type `geometry`) and time series data into GeoDataFrames, making them immediately available to the preprocessing pipeline.
- **Centralized Connection:** Database connection parameters are defined once in a central location in your configuration file.

## Configuration

To use this feature, you need to add two sections to your `config.yaml` file: `database_connection` and a `database_source` within a `global_inputs` item.

### 1. `database_connection`

This top-level section defines the connection parameters for your PostGIS database.

```yaml
database_connection:
  host: "localhost"
  port: 5432
  dbname: "gis_database"
  user: "myuser"
  password: "mypassword"
```

### 2. `database_source`

Instead of using the `file` keyword for a `global_inputs` item, you use the `database_source` keyword. This tells the parser to load this data from the database defined in `database_connection`.

The `database_source` must contain a `query` to be executed.

```yaml
global_inputs:
  subbasins_from_db:
    database_source:
      query: "SELECT zone_id, name, geometry FROM subbasins WHERE project_id = 123;"
    # You can still use the flexible mapping feature with database sources
    mapping:
      "name": "model_component_A"

  gauges_from_db:
    database_source:
      query: "SELECT station_id, x_coord, y_coord, geometry FROM rain_gauges;"
```

### Complete Example Snippet

Here is how these sections would look together in a `config.yaml`:

```yaml
# --- Database Connection (Top Level) ---
database_connection:
  host: "db.example.com"
  port: 5432
  dbname: "hydro_gis"
  user: "readonly_user"
  password: "password123"

# --- Global Inputs (with a mix of file and DB sources) ---
global_inputs:

  # Loading sub-basins from the database
  my_subbasins:
    database_source:
      query: "SELECT subbasin_id, area_sqkm, geometry FROM catchment_polygons WHERE model_run = 'calib_2023';"
    # Explicitly map the 'subbasin_id' column to a component named 'Main_Catchment'
    mapping:
      "subbasin_id": "Main_Catchment"

  # Loading time series data from a local file
  observed_flow:
    file: "data/local_flow_data.csv"

```

## Required Dependencies

To use the database integration feature, you must install the necessary Python libraries:
```bash
pip install SQLAlchemy GeoAlchemy2 psycopg2-binary
```
