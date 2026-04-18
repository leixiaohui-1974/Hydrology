# 水智大模型：Cursor 接入与逐算法调试计划

## 1. 目标定义（按你确认的口径）

- 对外定位：`水智大模型`（更易理解）
- 产品实体：`水智工坊`（可执行工作流体系）
- 接入目标：在 Cursor 内直接调用产品化工作流，不再依赖临时脚本
- 调试目标：按“一个算法一个算法”推进，形成可追溯的精度改进闭环

## 2. 已完成（可立即使用）

- 新增 MCP Server：`Hydrology/mcp_server.py`
- 新增 Cursor MCP 配置：`.cursor/mcp.json`
- 暴露的核心 MCP 工具：
  - `hm_list_workflows`：查看工作流注册表
  - `hm_list_agents`：查看 20 Agent 注册表
  - `hm_run_workflow`：执行产品化工作流
  - `hm_list_contracts`：查看案例产出
  - `hm_read_contract`：读取报告/结果文件
  - `hm_health`：健康检查
  - `hm_hos_compliance_report`：生成 HOS 工作流合规报告
  - `hm_hos_register_vendor_adapter`：注册第三方厂商适配器
  - `hm_hos_list_vendor_adapters`：查看已接入厂商列表

## 3. 启用步骤（本机一次配置）

1) 安装 MCP Python 依赖

```bash
/opt/homebrew/bin/python3.11 -m pip install mcp
```

2) 重启 Cursor（或刷新 MCP Server）

3) 在 Cursor 里验证可用性
- 先调 `hm_health`
- 再调 `hm_list_workflows`
- 最后用 `hm_run_workflow` 运行一个轻量工作流（如 `data_audit`）

## 4. 逐算法调试路线（建议执行顺序）

### 阶段 A：数据与几何基线

- 算法 1：断面解析与水力曲线（`section_analysis`）
  - 验证点：断面覆盖率、`A(H)` 单调性、5维质量评分
  - 产出：`contracts/section_*` 与知识固化文件

- 算法 2：数据质量审计（`data_audit`）
  - 验证点：缺测、异常、单位冲突、时间对齐
  - 产出：`contracts/data_quality_*`

### 阶段 B：D1 / D2 单体精度

- 算法 3：D1 水文率定/报告（`calibrate` / `hydro_report`）
  - 指标：NSE、RMSE、KGE
  - 门槛：NSE >= 0.85（可按 case 配置）

- 算法 4：D2 水力率定/报告（`hyd_cal` / `hyd_report`）
  - 指标：NSE、KGE、RMSE
  - 门槛：关键站点水位误差与趋势一致性

### 阶段 C：耦合与同化

- 算法 5：耦合计算（`coupled`）
  - 验证点：D1->D2 传递稳定、边界一致、无质量守恒漂移

- 算法 6：数据同化（`assimilate`）
  - 验证点：同化前后指标提升，稳定性不恶化

### 阶段 D：自学习闭环

- 算法 7：全管线自提升（`pipeline` / `dl_autolearn`）
  - 验证点：弱站点是否收敛、是否固化最佳策略、是否可复跑

## 5. 每个算法统一调试模板

每个算法都按以下 6 步执行，避免遗漏：

1. 基线运行（记录原始指标）
2. 诊断弱项（站点/变量/时段）
3. 多策略尝试（参数或模型）
4. 择优（保留最优并记录理由）
5. 固化（写入 `knowledge/` 与 `contracts/`）
6. 回归（确保不破坏既有站点）

## 6. 你现在就可以这样用

推荐第一轮（10-20 分钟可完成）：

1. `hm_health(case_id="daduhe")`
2. `hm_run_workflow(workflow="section_analysis", case_id="daduhe")`
3. `hm_run_workflow(workflow="data_audit", case_id="daduhe")`
4. `hm_run_workflow(workflow="hyd_cal", case_id="daduhe")`
5. `hm_list_contracts(case_id="daduhe")`
6. `hm_read_contract(case_id="daduhe", filename="<最新报告名>")`

## 7. 验收标准

- Cursor 中可稳定调用 MCP 工具，不依赖手工脚本
- 每个算法都有“前后指标 + 决策理由 + 固化结果”
- 新 case 只需配置+数据，不改代码
- 结果可追溯、可复现、可对比
