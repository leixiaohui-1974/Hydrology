# 水智工坊 (HydroMind Workshop)

> **写任何代码之前，先查 [PRODUCT_CATALOG.md](./PRODUCT_CATALOG.md) 和 [configs/agent_registry.yaml](./configs/agent_registry.yaml)。**
> 已有 168+ 个工作流 + 20 个 Agent，覆盖 12 个项目目录。不要重复造轮子。
> Agent 默认可见工作流以 [configs/agent_visible_workflows.yaml](./configs/agent_visible_workflows.yaml) 为准；兼容别名不直接对外暴露。

**统一入口：** `from workflows import run_workflow; run_workflow("<name>", case_id="<id>")`

| 关键词 | 产品 | 绝对禁止 |
|--------|------|---------|
| 断面/A(H)/水力曲线 | `hydro_model.section_analysis` | 手写过水面积计算 |
| 时序预测/LSTM | `hydro_model.dl_forecast` | 手写训练循环 |
| NSE/RMSE/精度 | `hydro_model.precision_evaluation` | 手写评价指标 |
| wxq JSON 解析 | `section_analysis.parsers` / `wxq_data_extractor` | 手写 JSON 解析 |
| Case 配置 | `workflows._shared.load_case_config` | 手写 YAML 加载 |
| 数据发现/知识挖掘 | `hydro_model.knowledge_engine` | 手写目录扫描 |
| SIL 闭环 | `pipedream_platform.runtime.sil_product` | 手写闭环循环 |
| MPC 控制 | `cascade_mpc_product` / `hydroe2e.controllers` | 手写控制器 |
| 系统辨识 | `identification` 模块族 | 手写 EKF/RLS |
| ODD 评估 | `odd_product` / `HydroMAS.core.odd` | 手写工况判定 |

---

## Agent 团队

水利数字化全生命周期由 **20 个 Agent** 分工协作，分三层组织。

### 全局流转图

```
协智 (编排)
  ↓
开局 → 探源(持续) → 识地 → 筑模
                                ↓
                        率定 ←→ 审评
                                ↓
            探源(持续) → 推演 → 预见 → 撰报
                          ↓              ↓
                        辨识 → 驭控     固知
                          ↓
                  域界 → 闭环 → 验模
                          ↓
                  调度 → 管线 → 护安
                                ↓
                              求解 (底层引擎)
```

### 第一层：建模核心（Hydrology/）

| # | 名称 | CLI 别名 | 副标题 | 阶段 |
|---|------|---------|--------|------|
| 1 | **探源** | tanyuan | 数据勘探与知识发现 | 全程 |
| 2 | **开局** | kaiju | 案例初始化与配置生成 | 初始化 |
| 3 | **固知** | guzhi | 知识固化与资产管理 | 固化 |
| 4 | **识地** | shidi | 地形分析与 DEM 处理 | 数据准备 |
| 5 | **筑模** | zhumo | 模型构建与拓扑组装 | 建模 |
| 6 | **率定** | luding | 参数校准与自学习 | 率定 |
| 7 | **推演** | tuiyan | 水力仿真与耦合计算 | 仿真 |
| 8 | **预见** | yujian | 智能预报与预警 | 预报 |
| 9 | **审评** | shenping | 精度评估与质量审核 | 评估 |
| 10 | **撰报** | zhuanbao | 成果报告自动生成 | 报告 |

### 第二层：控制与自动化（pipedream-lab / E2EControl / HIL / YJDT）

| # | 名称 | CLI 别名 | 副标题 | 阶段 | 核心项目 |
|---|------|---------|--------|------|---------|
| 11 | **辨识** | bianshi | 系统辨识与参数辨识 | 辨识 | pipedream, E2EControl, HydroClaude, YJDT |
| 12 | **调度** | diaodu | 优化调度与实时派发 | 调度 | pipedream, HydroMAS, YJDT |
| 13 | **驭控** | yukong | 自适应控制与 MPC | 控制 | pipedream, E2EControl, HydroClaude |
| 14 | **闭环** | bihuan | SIL 闭环仿真与验证 | 仿真验证 | pipedream, E2EControl, HIL |
| 15 | **域界** | yujie | ODD 运行设计域评估 | 评估 | pipedream, HydroMAS, YJDT, HIL |
| 16 | **验模** | yanmo | MBD 模型验证与对标 | 验证 | HIL, YJDT, HydroClaude, E2EControl |

### 第三层：集成产品（跨项目）

| # | 名称 | CLI 别名 | 副标题 | 阶段 | 核心项目 |
|---|------|---------|--------|------|---------|
| 17 | **求解** | qiujie | 水动力核心求解引擎 | 求解 | HydroClaude |
| 18 | **管线** | guanxian | 端到端全流程管线 | 集成 | pipedream, E2EControl |
| 19 | **护安** | huan | 监控告警与安全守护 | 运维 | HydroGuard, HydroPortal |
| 20 | **协智** | xiezhi | 多智能体编排与科研 | 编排 | HydroMAS, agent-teams, AutoResearch |

### 项目 × Agent 矩阵

```
                    探 开 固 识 筑 率 推 预 审 撰 辨 调 驭 闭 域 验 求 管 护 协
                    源 局 知 地 模 定 演 见 评 报 识 度 控 环 界 模 解 线 安 智
Hydrology           ●  ●  ●  ●  ●  ●  ●  ●  ●  ●
pipedream-lab                                       ●  ●  ●  ●  ●        ●
E2EControl                                          ●     ●  ●     ●     ●  ●
HydroClaude                                   ●     ●     ●        ●  ●
HydroMAS                                               ●        ●              ●
YJDT                                                ●  ●        ●  ●
HIL                                                          ●  ●  ●
HydroGuard                                                                  ●
HydroPortal                                                                 ●
agent-teams                                                                    ●
AutoResearch                                                                   ●
```

### Agent 注册表

完整的元数据（模块映射、workflow 清单、受众、描述）见 [`configs/agent_registry.yaml`](./configs/agent_registry.yaml)。

### 命名规范

- 每个 workflow 文件 docstring 首行标注所属 Agent（如 `"""探源 (TanYuan) — 数据勘探与知识发现"`）
- 新增 workflow 前必须先确定归属 Agent，写入注册表
- 一个 workflow 只属于一个 Agent
- 跨项目的 workflow 按**主要功能**归属，而非按物理目录

---

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Hydrology** (6873 symbols, 20507 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Hydrology/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Hydrology/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Hydrology/clusters` | All functional areas |
| `gitnexus://repo/Hydrology/processes` | All execution flows |
| `gitnexus://repo/Hydrology/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
