# HydroMind 产品目录

> **本文件是所有 AI Agent 的必读参考。**
> 写代码前先查这里。已有的产品直接调用，不要从零实现。

## 快速入口

```python
# 统一工作流入口（推荐）
from workflows import run_workflow, list_workflows
run_workflow("<name>", case_id="<case_id>")

# 查看所有可用工作流
for wf in list_workflows():
    print(f"{wf['name']:20s} {wf['description']}")
```

```bash
# CLI 通用格式
cd Hydrology && python3 -m workflows.run_<name> --case-id <case_id>
```

---

## 一、产品模块（hydro_model.*）

### 1. section_analysis — 断面分析

**解决什么问题：** 从多种格式的原始断面数据，计算 A(H)/P(H)/B(H)/R(H) 水力曲线，评估数据质量。

| 组件 | 路径 | 作用 |
|------|------|------|
| SectionProfile | `section_analysis.base` | 统一断面数据模型 |
| SectionAnalysisConfig | `section_analysis.config` | 配置（从 Case YAML 注入） |
| parsers | `section_analysis.parsers` | 4 种格式解析器注册表 |
| hydraulics | `section_analysis.hydraulics` | 水力计算引擎（纯函数） |
| evaluator | `section_analysis.evaluator` | 5 维质量评估 |
| run_section_pipeline | `section_analysis` | 全流程（解析→计算→评估） |

**解析器注册表：**
- `wxq_json` — wxq 智能体 JSON（含 baseData.sections）
- `terrain_txt` — "断面 X" 格式 TXT
- `wxq_terrain_txt` — wxq 导出河道地形 TXT（梯形+不规则形）
- `xlsx_terrain` — Excel 河道地形

**API 示例：**
```python
from hydro_model.section_analysis.hydraulics import compute_hydraulic_properties
# yz: list[list[float]]，每点为 [横距, 高程]
hp = compute_hydraulic_properties(yz, water_level=850.0, manning_n=0.025)
# hp.A=面积, hp.P=湿周, hp.B=水面宽, hp.R=水力半径, hp.Q=Manning流量
```

**扩展方式：** 新增数据格式只需实现 `BaseSectionParser` 协议并 `register_parser("name", MyParser)`。

---

### 2. dl_forecast — 深度学习时序预测

**解决什么问题：** 对水位/流量等时间序列建模预测。

| 组件 | 路径 | 作用 |
|------|------|------|
| ForecastConfig | `dl_forecast.config` | 模型超参配置 |
| TimeSeriesDataset | `dl_forecast.dataset` | 滑动窗口数据集 |
| build_model | `dl_forecast` | 从 MODEL_REGISTRY 构建模型 |
| ForecastEvaluator | `dl_forecast.evaluator` | NSE/RMSE/MAE/R² 评价 |
| transfer | `dl_forecast.transfer` | 迁移学习（预训练/微调/零样本） |
| AutoLearner | `dl_forecast.autolearn` | 自学习闭环 |

**已注册模型：** lstm / transformer / timesfm

**API 示例：**
```python
from hydro_model.dl_forecast import build_model, ForecastConfig
cfg = ForecastConfig(model_type="lstm", seq_len=168, horizon=24, epochs=100)
model = build_model(cfg)
model.fit(train_ds)
preds = model.predict(test_ds)
```

**扩展方式：** 新增模型只需继承 `BaseForecastModel` 并 `register_model("name", MyModel)`。

---

### 3. reservoir_balance — 水库水量平衡

**解决什么问题：** 水库逐时段水量平衡计算与率定。

```python
from hydro_model.reservoir_balance import ReservoirBalanceModel, calibrate_station
import numpy as np
model = ReservoirBalanceModel(A_eff=1e7, alpha=0.8, beta=0.01)
H_sim = model.simulate(Q_in, Q_out, H0=500.0, dt=3600.0)
result = calibrate_station(Q_in, Q_out, H_obs, cal_ratio=0.7)
```

---

### 4. terrain_analysis + dem_pipeline — DEM/地形

**解决什么问题：** DEM 处理、流域划分、子流域提取。

```python
from hydro_model import TerrainAnalyzer, DEMPipeline
# DEMPipeline 加载 case DEM → DEMData；TerrainAnalyzer 无参构造后 load_dem
pipe = DEMPipeline(case_id="daduhe")
dem = pipe.load()
analyzer = TerrainAnalyzer()
analyzer.load_dem(dem)
flow = analyzer.compute_flow_direction()
basins = analyzer.delineate_basins(
    flow,
    outlets=[{"name": "out1", "lon": 103.0, "lat": 29.0}],
    subtract_upstream=True,
)
```

---

### 5. enkf — 数据同化

**解决什么问题：** 集合卡尔曼滤波器实时校正。

```python
from hydro_model.enkf import EnsembleKalmanFilter
import numpy as np
ekf = EnsembleKalmanFilter(n_ensemble=50)
ekf.initialize(initial_states)  # shape (n_states, n_ensemble)
forecast_obs = ekf.forecast(model_forward, **kwargs)
ekf.analysis(observation, forecast_obs, R)  # R 为观测误差协方差
```

---

### 6. precision_evaluation — 精度评价

**解决什么问题：** 流域划分 / 时序模拟等综合精度评价；单点指标见 `calibration` / `ForecastEvaluator`。

```python
from hydro_model.calibration import nse, rmse, kge, compute_all_metrics
from hydro_model.precision_evaluation import evaluate_timeseries
metrics = compute_all_metrics(observed, simulated)  # 含 nse, rmse, kge, mae, r2, pbias
acc = evaluate_timeseries(observed, simulated)
nse_val = acc.metrics["nse"]
```

---

### 7. runoff + routing — 产汇流

**解决什么问题：** 产流（SCS/新安江）+ 汇流（Muskingum/单位线）。

```python
from hydro_model.runoff import SCSCurveNumberModule
from hydro_model.routing import MuskingumRouting
scs = SCSCurveNumberModule(cn=75)
musk = MuskingumRouting(k=3600, x=0.2)
```

---

### 8. report_md + report_template — 报告生成

- **业务向长文汇编**：`hydro_model.business_run_digest` + `workflow_smart_reporting.yaml` 的 `business_run_digest` 章节；CLI / 注册表 `business_run_digest`；拓扑六类样本刷新 `object_topology_report`（`generate_object_topology_report`）。

**解决什么问题：** 自动生成 Markdown 格式精度报告。

```python
from hydro_model.report_md import ReportGenerator
gen = ReportGenerator(case_id="daduhe", dimension="D2")
md = gen.build(station_results=..., summary=...)
gen.write("cases/daduhe/contracts/D2_hydraulic_report.md")
```

---

### 9. wxq_data_extractor + knowledge_mining — 数据提取

**解决什么问题：** 从 wxq 平台 JSON 批量提取拓扑、水力学与报告（写入知识目录）。

```python
from hydro_model.wxq_data_extractor import extract_all
report = extract_all(wxq_json_path, case_id="daduhe")  # 含 topology 等写入结果摘要
```

---

### 10. curve_calibration — 曲线率定

**解决什么问题：** Z-V/Z-Q 等特征曲线插值、多项式拟合与迭代率定。

```python
from hydro_model.curve_calibration import Curve, fit_polynomial, calibrate_curve_iterative
coeffs = fit_polynomial(z_data, v_data, degree=3)
design = Curve(name="zv", curve_type="zv", station="s1", x=z_data, y=v_data)
result = calibrate_curve_iterative(design, obs_z, obs_v)
```

---

## 二、工作流注册表（workflows.*）

| 名称 | 功能 | CLI |
|------|------|-----|
| `init` | 案例初始化 | `--case-id X --wxq-dir Y` |
| `model` | 水文+水动力建模 | `--case-id X` |
| `calibrate` | 逐站率定验证 | `--case-id X` |
| `improve` | 精度自提升 | `--case-id X` |
| `cascade` | 梯级全自主运行 | `--case-id X` |
| `pipeline` | 自学习管线 | `--case-id X` |
| `consolidate` | 知识固化 | `--case-id X` |
| `selfdiag` | 水动力自诊断 | `--case-id X` |
| `d1d4` | D1-D4 精度报告 | `--case-id X` |
| `wxq_mine` | wxq 知识挖掘 | `--case-id X` |
| `state_est` | 状态估计 EKF | `--case-id X` |
| `assimilate` | 数据同化比选 | `--case-id X` |
| `deep_record` | 深度资产记录 | `--case-id X` |
| `registry` | 知识注册表 | `--case-id X` |
| `hyd_cal` | 水力学率定 | `--case-id X` |
| `hyd_report` | D2 水力学报告 | `--case-id X` |
| `hydro_report` | D1 水文报告 | `--case-id X` |
| `coupled` | 水文水力学耦合 | `--case-id X` |
| `data_audit` | 数据质量审计 | `--case-id X` |
| `dl_forecast` | DL 时序预测 | `--case-id X` |
| `section_analysis` | 断面分析 | `--case-id X` |
| `ensemble_forecast` | 集合预报 | `--case-id X` |
| `dl_transfer` | 迁移学习 | `--case-id X` |
| `dl_autolearn` | DL 自学习 | `--case-id X` |

以上 **24** 项与 `workflows/__init__.py` 中 `WORKFLOW_REGISTRY` 键名一一对应。

### Smart 编排与跑后报告（配置驱动）

| 能力 | 配置 / 模块 | 说明 |
|------|-------------|------|
| 中文计划与自动选流 | `configs/workflow_catalog_zh.yaml` + `python3 -m workflows.run_workflow_smart_zh` | `meta`（CLI 契约 JSON）·`plan` / `run` / `menu` / `legend` / `list` / `refresh-reports`；`plan`/`run`/`menu`/`refresh-reports` 支持 `--json-summary` → `contracts/workflow_smart_cli_result.latest.json` |
| 跑后报告链与 `refresh-reports` | `configs/workflow_smart_reporting.yaml` + 案例 YAML 可选 `smart_reporting:` | 合并顺序：`defaults` ← `per_case.<case_id>` ← 案例块；API：`workflows.smart_run_reporting.load_workflow_smart_reporting_config`、`emit_post_run_artifacts`、`regenerate_md_dimension_reports` |
| 仅刷新报告 | `refresh-reports --case-id …` | 依赖 `contracts/workflow_smart_run_summary.latest.json`；`--regenerate-md-reports` 按配置中的 `md_regeneration.workflow_keys` 调用注册表入口（排除 `external_script`） |

---

## 三、共享基础设施

| 模块 | 路径 | 作用 |
|------|------|------|
| `load_case_config` | `workflows._shared` | 加载 Case YAML + 知识层合并 |
| `save_knowledge_file` | `workflows._shared` | 写入知识目录 YAML |
| `write_json` | `workflows._shared` | 写入 JSON（自动创建目录） |
| `resolve_config_paths` | `workflows._shared` | 相对路径→绝对路径 |

---

## 四、输出约定

- **合约文件：** `cases/{case_id}/contracts/{workflow}.latest.json`
- **知识文件：** `Hydrology/knowledge/{case_id}/{domain}/{file}.yaml`
- **模型权重：** `cases/{case_id}/models/{model_type}/`
- **报告文件：** `cases/{case_id}/contracts/{report_name}.md`

所有输出必须带 `_auto_generated` 和 `_generated_at` 元数据。

---

## 五、扩展产品的正确方式

### 新增断面解析器
```python
from hydro_model.section_analysis.parsers import register_parser
class MyParser:
    @staticmethod
    def can_handle(path): return path.endswith(".xyz")
    def parse(self, path, **kwargs): return [SectionProfile(...)]
register_parser("xyz_format", MyParser)
```

### 新增 DL 模型
```python
from hydro_model.dl_forecast import register_model
from hydro_model.dl_forecast.base import BaseForecastModel
class MyModel(BaseForecastModel):
    def fit(self, ds): ...
    def predict(self, ds): ...
register_model("my_model", MyModel)
```

### 新增工作流
在 `workflows/__init__.py` 的 `WORKFLOW_REGISTRY` 中添加条目即可。
