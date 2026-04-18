# HydroMind Open Standard (HOS) v1.0

## 1. 定位

HOS 是水智工坊的开放接入标准，目标是：

- 支持行业内第三方模型/工作流无缝接入
- 保证输入输出契约统一、单位统一、可审计可追溯
- 同题同数据同评分，形成可比较的行业基准

## 2. 分层标准

### HOS-L1: Adapter 接入标准

- 每个厂商必须提供 `vendor_id`、`name`、`adapter_type`
- 必须声明 `unit_system=SI`
- 必须提供能力清单 `workflows`（可执行 workflow_id 列表）

### HOS-L2: 数据契约标准

- 案例入口必须含 `case_id`
- 输出必须写入 `cases/{case_id}/contracts/`
- 输出必须带 `_auto_generated=true`

### HOS-L3: 工作流契约标准

- 每个 workflow 必须有：
  - `workflow_id/module/entrypoint`
  - `inputs.required`（必须包含 `case_id`）
  - `runtime.timeout_seconds`

### HOS-L4: 评测标准

- 统一指标口径：NSE/KGE/RMSE/稳定性/成本
- 报告可回放，含参数与版本信息

### HOS-L5: 治理标准

- 标准版本化：`hos_version`
- 适配器注册表配置化：`configs/vendor_adapters.yaml`

## 3. 产品内落地能力（已实现）

- `hm_hos_compliance_report`：生成工作流合规报告
- `hm_hos_register_vendor_adapter`：注册第三方厂商适配器
- `hm_hos_list_vendor_adapters`：列出已注册适配器
- `hm_run_workflow`：执行时附带 `_hos` 标准元数据

## 4. 最小接入示例

```json
{
  "vendor_id": "demo_vendor",
  "name": "Demo Vendor",
  "adapter_type": "python",
  "unit_system": "SI",
  "workflows": ["flood_forecast", "reservoir_dispatch"],
  "status": "active"
}
```
