# 数据库集成 (PostGIS)

对于更大和更专业的项目，使用数据库管理空间和时间序列数据通常比使用本地文件更可取。该框架支持直接从PostGIS数据库加载数据。

## 功能概述

- **直接加载:** 数据源可以定义为针对指定PostGIS数据库执行的SQL查询。
- **GeoPandas集成:** 框架使用`GeoPandas`和`GeoAlchemy2`自动将空间数据(即`geometry`类型的列)和时间序列数据读取到GeoDataFrames中，使其立即可用于预处理流水线。
- **集中连接:** 数据库连接参数在配置文件的中央位置定义。

## 配置

要使用此功能，您需要在`config.yaml`文件中添加两个部分：`database_connection`和`global_inputs`项目中的`database_source`。

### 1. `database_connection`

这个顶层部分定义了PostGIS数据库的连接参数。

```yaml
database_connection:
  host: "localhost"
  port: 5432
  dbname: "gis_database"
  user: "myuser"
  password: "mypassword"
```

### 2. `database_source`

在`global_inputs`项目中，使用`database_source`关键字代替`file`关键字。这告诉解析器从`database_connection`中定义的数据库加载此数据。

`database_source`必须包含要执行的`query`。

```yaml
global_inputs:
  subbasins_from_db:
    database_source:
      query: "SELECT zone_id, name, geometry FROM subbasins WHERE project_id = 123;"
    # 您仍然可以在数据库源中使用灵活的映射功能
    mapping:
      "name": "model_component_A"

  gauges_from_db:
    database_source:
      query: "SELECT station_id, x_coord, y_coord, geometry FROM rain_gauges;"
```

### 完整示例片段

以下是`config.yaml`中这些部分的组合方式：

```yaml
# --- 数据库连接 (顶层) ---
database_connection:
  host: "db.example.com"
  port: 5432
  dbname: "hydro_gis"
  user: "readonly_user"
  password: "password123"

# --- 全局输入 (混合文件和数据库源) ---
global_inputs:

  # 从数据库加载子流域
  my_subbasins:
    database_source:
      query: "SELECT subbasin_id, area_sqkm, geometry FROM catchment_polygons WHERE model_run = 'calib_2023';"
    # 显式将'subbasin_id'列映射到名为'Main_Catchment'的组件
    mapping:
      "subbasin_id": "Main_Catchment"

  # 从本地文件加载时间序列数据
  observed_flow:
    file: "data/local_flow_data.csv"

```

## 所需依赖项

要使用数据库集成功能，您必须安装必要的Python库：
```bash
pip install SQLAlchemy GeoAlchemy2 psycopg2-binary
```