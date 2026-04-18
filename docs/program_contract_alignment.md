# Hydrology Program Contract Alignment

这个文档定义 `Hydrology` 仓当前如何与 `HydroMind` 项目群的统一对象对齐。

目标不是一次重构完全部实现，而是先给本仓建立一条稳定语义线：

`Case -> Data Pack -> Run -> Review -> Release`

## Current Situation

`Hydrology` 目前已经有 3 类重要入口，但对象语义还没有统一。

### 1. 配置驱动模拟入口

- [common/config_parser.py](/Users/rainfields/hydrosis-local/research/Hydrology/common/config_parser.py)
- [run_from_config.py](/Users/rainfields/hydrosis-local/research/Hydrology/run_from_config.py)

现状：

- 能从 YAML 组装 simulation controller
- 更像“组件装配配置”
- 还不是项目群统一的 `WorkflowRun`

### 2. 脚本式流水线入口

- [examples/run_full_pipeline.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/run_full_pipeline.py)
- [examples/run_workflow_baseline.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/run_workflow_baseline.py)
- [examples/generate_parameter_zones.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/generate_parameter_zones.py)

现状：

- 已经形成事实上的流域划分和水文模拟工作流
- 但输入输出关系散在脚本和 CSV/Shapefile 约定里
- 还没有统一到 `Data Pack / Run / Artifact`

Phase 01 决策：

- `examples/run_full_pipeline.py` 保留为实际实现
- `examples/run_workflow_baseline.py` 作为正式 workflow baseline 入口名
- 当前不再新起一层 runner 抽象，先把对象模型和交付面稳定下来

### 3. 报告与人工验收入口

- [hydro_model/report_template.py](/Users/rainfields/hydrosis-local/research/Hydrology/hydro_model/report_template.py)
- [examples/generate_html_report.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/generate_html_report.py)
- [docs/daduhe_watershed_report.md](/Users/rainfields/hydrosis-local/research/Hydrology/docs/daduhe_watershed_report.md)
- [docs/us_small_watershed_report.md](/Users/rainfields/hydrosis-local/research/Hydrology/docs/us_small_watershed_report.md)

现状：

- 已经有很强的浏览器可读报告面
- 但还没有明确映射到统一 `ReviewBundle`

## Target Mapping

### `Case`

本仓不作为 `CaseManifest` 的主定义仓。

`Hydrology` 只消费 `CaseManifest`：

- 用于识别案例 ID / display name / raw root
- 不在本仓重复定义 schema

### `Data Pack`

本仓消费 `SourceBundle` 或更高层标准数据集。

最小输入面：

- DEM / 河网 / 子流域边界
- 土地利用 / 土壤
- 雨量站 / 水文站
- 降雨 / PET / 流量时序

对于 `daduhe/watershed_delineation`，当前最小可执行输入面固定为：

- `Case`: case manifest / case id
- `Data Pack`: `source_bundle.contract.json`
- `Data Pack`: `outlets.normalized.json`
- `Review gate`: `basin_validation_report.json` 与 source reliability 结论

### `Run`

本仓应逐步把两类运行统一映射为 `WorkflowRun`：

1. `watershed_delineation`
2. `hydrological_simulation`

最小结构化落点：

- run_id
- case_id
- workflow_type
- inputs
- outputs
- steps
- started_at / completed_at
- metadata

`watershed_delineation` 这一条特别要求：

- 主引擎目标是 `WhiteboxTools`
- `pysheds` 只可作为 legacy/reference，不应成为 workflow 完成态的判据

### `Review`

本仓的 HTML 报告与人工验收应逐步映射为 `ReviewBundle`：

- `review_id`
- `run_id`
- `case_id`
- `verdict`
- `findings`
- `report_artifacts`

### `Release`

本仓不作为 `ReleaseManifest` 主生成仓。

它负责提供：

- 可发布 artifact
- report artifact
- run artifact metadata

最终 release 由数据平台层统一登记。

## Minimal Integration Rules

### Rule 1

新的 workflow 文档和示例，优先使用统一术语：

- `Case`
- `Data Pack`
- `Run`
- `Review`
- `Release`

### Rule 2

新的浏览器报告或验收文档，应明确：

- 它属于哪个 `run_id`
- 它对应哪个 `case_id`
- 它在 `ReviewBundle.report_artifacts` 中如何登记

### Rule 3

新的脚本入口，不再自己发明对象名字；需要引用 program contracts 时，统一通过：

- [common/program_contract_bridge.py](/Users/rainfields/hydrosis-local/research/Hydrology/common/program_contract_bridge.py)

## Bridge Entry

本仓新增的 program-contract bridge：

- [common/program_contract_bridge.py](/Users/rainfields/hydrosis-local/research/Hydrology/common/program_contract_bridge.py)

它提供：

- `CONTRACTS_AVAILABLE`
- `PROGRAM_SCHEMA_VERSION`
- `load_and_validate_payload(kind, path)`
- `validate_payload(kind, payload)`
- `program_contract_kinds()`

支持的 `kind`：

- `case_manifest`
- `source_bundle`
- `workflow_run`
- `review_bundle`
- `release_manifest`

## Next Implementation Steps

1. 让 workflow spec 明确消费 `Case / Data Pack` 并约束最小输入面
2. 让 `run_workflow_baseline.py` 作为 Daduhe MVP 的正式 baseline 入口名
3. 给 `run_from_config.py` 增加 contract-aware run wrapper
4. 给 `report_template` 补 report artifact / review metadata 映射

---
status: active  
scope: repo  
source_of_truth: yes
