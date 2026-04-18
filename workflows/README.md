# Hydrology Workflows

这一层是 `Hydrology` 的确定性 workflow 入口。

## 业务人员快速开始

如果你只想记住一件事：

> **以后默认用 `python3 -m workflows.run_workflow_smart_zh ...`，不要从零散 workflow 脚本开始。**

建议按这个顺序使用：

### 1) 先看系统支持什么

```bash
python3 -m workflows.run_workflow_smart_zh legend
python3 -m workflows.run_workflow_smart_zh meta
```

- `legend`：看“智能 / 仿真 / 控制 / 评价 / 全量”分别是什么意思
- `meta`：给 Claude Code / Codex / 网关读取稳定契约

### 2) 先出计划，不要一上来就跑

```bash
python3 -m workflows.run_workflow_smart_zh plan --case-id daduhe --json-summary
```

这一步会生成：

- `workflow_smart_plan.latest.json`
- `workflow_smart_plan_report.latest.md`
- `workflow_smart_plan_report.latest.html`
- `workflow_smart_cli_result.plan.smart.latest.json`

说明：`--json-summary` 现在总会写当前命令/模式的 scoped 摘要；只有正式 `run --profile smart`（非 `--dry-run`）才会额外刷新共享的 `workflow_smart_cli_result.latest.json`。

### 3) 再执行一键建模

```bash
python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --profile smart --json-summary
```

如果你只是想先看会跑哪些步骤，用：

```bash
python3 -m workflows.run_workflow_smart_zh run --case-id daduhe --profile smart --dry-run --json-summary
```

### 4) 改报告策略后，优先刷新，不要重跑

```bash
python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id daduhe --json-summary
```

## Claude Code / 网关接入

如果你希望让 Claude Code 通过统一入口驱动 smart CLI，可用 `agent_loop_gateway.py`。

如果当前目录在仓库根 `research/`，执行：

```bash
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"list_tools","case_id":"daduhe"}'
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"invoke_tool","tool":"smart_meta"}'
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"invoke_tool","tool":"smart_plan","case_id":"daduhe"}'
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"invoke_tool","tool":"smart_run","case_id":"daduhe"}'
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"invoke_tool","tool":"smart_refresh_reports","case_id":"daduhe"}'
python3 Hydrology/workflows/agent_loop_gateway.py --oneshot '{"op":"invoke_tool","tool":"smart_status","case_id":"daduhe"}'
```

如果当前目录已经在 `Hydrology/workflows/`，则可把前缀路径省略。

网关会做两件事：

- 把稳定 CLI 收口成统一工具面，方便 Claude Code / 类 Codex 调用
- 按 `agent_visible_workflows.yaml` 与 case `manifest.yaml` 做可见性和治理约束

## 跑完后先看什么

业务人员优先阅读：

- `cases/<case_id>/contracts/business_run_digest.latest.md`
- `cases/<case_id>/contracts/E2E_LIVE_DASHBOARD.html`
- `cases/<case_id>/contracts/workflow_smart_report.latest.md`
- `cases/<case_id>/contracts/final_report.latest.json`

机器/Agent 优先读取：

- `cases/<case_id>/contracts/workflow_smart_cli_result.<command>.<profile>[.dry_run].latest.json` — 当前命令/模式作用域摘要
- `cases/<case_id>/contracts/workflow_smart_cli_result.latest.json` — 正式 smart run 的共享 latest
- `cases/<case_id>/contracts/workflow_smart_run_summary.latest.json`
- `cases/<case_id>/contracts/workflow_smart_progress.latest.ndjson`

目标：

- 把 `Case / Data Pack / Run / Review / Release` 的主干固定成脚本
- 把 runner 选择、输入面、输出路径、contract 写入、编排顺序从 prompt 和人工习惯里拿出来
- 允许大模型做诊断、解释、建议，但不让它决定状态机

当前入口：

- `build_data_pack.py`
- `run_watershed_delineation.py`
- `run_hydrological_simulation.py`
- `build_review_bundle.py`
- `build_release_manifest.py`
- `run_case_pipeline.py`

中文用户 / 自动选流：

- `python3 -m workflows.run_workflow_smart_zh meta` — **无需 `--case-id`**：打印 Agent/CI 可用的 JSON 契约（子命令、产物相对路径、`HYDRO_SMART_JSON_SUMMARY`、退出码约定）
- `python3 -m workflows.run_workflow_smart_zh plan … --json-summary` / `run … --json-summary` / `menu … --json-summary` / `refresh-reports … --json-summary` — 总是写当前命令/模式的 scoped 摘要 `cases/<案例>/contracts/workflow_smart_cli_result.<command>.<profile>[.dry_run].latest.json`；只有正式 `run --profile smart`（非 `--dry-run`）才额外刷新共享的 `cases/<案例>/contracts/workflow_smart_cli_result.latest.json`；加 `--print-json-summary` 可额外 stdout 一行 JSON
- `python3 -m workflows.run_workflow_smart_zh legend` — 端到端范围说明与「该怎么说」示例
- `python3 -m workflows.run_workflow_smart_zh plan --case-id <案例>` — 根据 **数据就绪度** + **建模提示**（无提示时用 **启发式**）生成中文计划，写入 `cases/<案例>/contracts/workflow_smart_plan.latest.json`
- `python3 -m workflows.run_workflow_smart_zh run --case-id <案例> --dry-run` — 仅预览；去掉 `--dry-run` 则按计划依次 `run_workflow`
- `python3 -m workflows.run_workflow_smart_zh menu --case-id <案例>` — 交互式固定菜单选 profile（智能 / 仿真 / 控制 / 评价 / 全量）
- `python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id <案例>` — **不重跑工作流**，从 `workflow_smart_run_summary` + plan 刷新 E2E 看板 / 验证 / `final_report` / 索引；改策略后优先用这个
- `python3 -m workflows.run_workflow_smart_zh refresh-reports --case-id <案例> --regenerate-md-reports` — 先按配置重跑 D1/D2/D1–D4 等 **Markdown 生成器**（走 `WORKFLOW_REGISTRY`），再刷新跑后报告链
- 目录与标签：`configs/workflow_catalog_zh.yaml`
- **跑后报告与 refresh 行为（脚本路径、合约文件名、`md_regeneration.workflow_keys`、索引链接模板等）：** `configs/workflow_smart_reporting.yaml`；案例可在自身 YAML 顶层加 `smart_reporting:` 覆盖；CLI 可用 `--smart-reporting-config` / `--case-config` 指向自定义文件（相对 workspace 根）

原则：

- workflow 入口必须有稳定 CLI
- 输入路径、输出路径、必需 gate、workflow_type 由脚本固定
- 业务实现可暂时复用 `examples/` 或现有 runner，但调用边界由本目录统一定义