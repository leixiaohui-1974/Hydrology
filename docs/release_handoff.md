# Hydrology Release Handoff

这个文档定义 `Hydrology` 如何把运行产物交给 `kb_pipeline` 做正式 release 登记。

当前原则很简单：

- `Hydrology` 负责生成标准 JSON 和成果文件
- `kb_pipeline` 负责导入、登记、发布
- 不让 `Hydrology` 直接写数据库

## Current Handoff Files

### Workflow run metadata

- `workflow_run.json`

来源：

- [run_from_config.py](/Users/rainfields/hydrosis-local/research/Hydrology/run_from_config.py)
- [run_full_pipeline.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/run_full_pipeline.py)
- [run_workflow_baseline.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/run_workflow_baseline.py)

### Review metadata

- `review_bundle.json`

来源：

- [generate_html_report.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/generate_html_report.py)

### Release metadata

- `release_manifest.json`

来源：

- [build_release_manifest.py](/Users/rainfields/hydrosis-local/research/Hydrology/examples/build_release_manifest.py)

## Minimal Flow

1. 运行 workflow baseline，得到 `workflow_run.json`
2. 生成报告，得到 `review_bundle.json`
3. 组装 release，得到 `release_manifest.json`
4. 用 `kb_pipeline` 导入 release manifest

## Example

先在 `Hydrology` 仓生成 release manifest：

```bash
cd /Users/rainfields/hydrosis-local/research/Hydrology

python3 examples/run_workflow_baseline.py --case-id daduhe

python3 examples/build_release_manifest.py \
  --case-id daduhe \
  --version v1.0.0 \
  --workflow-run examples/results/pipeline.workflow_run.json \
  --review-bundle examples/results/hydrology_report.review_bundle.json \
  --artifact examples/results/pipeline_simulation_results.csv \
  --artifact examples/results/flow_comparison.png
```

再在 `kb_pipeline` 导入：

```bash
cd /Users/rainfields/hydrosis-local/research/pipedream-hydrology-integration-lab

python3 -m kb_pipeline.cli release daduhe --manifest-json \
  /Users/rainfields/hydrosis-local/research/Hydrology/examples/results/hydrology_report.release_manifest.json
```

## What Must Be In The Manifest

最小必须包括：

- `release_id`
- `case_id`
- `version`
- `channel`
- `status`
- `included_runs`
- `review_refs`
- `artifacts`

## Product Boundary

### Hydrology

负责：

- 运行 workflow
- 生成报告
- 组织 release manifest

### kb_pipeline

负责：

- 校验并导入 release manifest
- 发布登记
- 后续数据库治理与分发

---
status: active  
scope: repo  
source_of_truth: yes
