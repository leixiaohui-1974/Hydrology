"""HydroMind Open Standard (HOS) runtime helpers.

把“标准体系”变成可执行能力，而不是纯文档：
- 统一工作流契约生成与校验
- 厂商适配器注册与持久化
- 合规报告生成
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import yaml


HOS_VERSION = "1.0.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_workflow_contract(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """从 WORKFLOW_REGISTRY 条目构建 HOS 工作流契约。"""
    required_args = spec.get("required_args", [])
    module = spec.get("module", "")
    entry = spec.get("entry", "")
    return {
        "hos_version": HOS_VERSION,
        "contract_type": "workflow",
        "workflow_id": name,
        "module": module,
        "entrypoint": entry,
        "description": spec.get("description", ""),
        "inputs": {
            "required": required_args,
            "optional": [],
            "unit_system": "SI",
            "case_id_required": "case_id" in required_args,
        },
        "outputs": {
            "schema": "opaque_json",
            "contracts_dir": "cases/{case_id}/contracts/",
            "_auto_generated": True,
        },
        "runtime": {
            "idempotent": True,
            "retryable": True,
            "timeout_seconds": 1800,
        },
        "provenance": {
            "generated_at": _utc_now(),
            "source": "WORKFLOW_REGISTRY",
        },
    }


def validate_workflow_contract(contract: dict[str, Any]) -> list[str]:
    """返回校验错误列表；空列表表示通过。"""
    errors: list[str] = []
    required_top = [
        "hos_version",
        "contract_type",
        "workflow_id",
        "module",
        "entrypoint",
        "inputs",
        "outputs",
        "runtime",
        "provenance",
    ]
    for key in required_top:
        if key not in contract:
            errors.append(f"missing top-level field: {key}")

    if contract.get("contract_type") != "workflow":
        errors.append("contract_type must be 'workflow'")

    inputs = contract.get("inputs", {})
    if not isinstance(inputs.get("required", []), list):
        errors.append("inputs.required must be list")
    if "case_id" not in inputs.get("required", []):
        errors.append("inputs.required must include case_id")
    if inputs.get("unit_system") != "SI":
        errors.append("inputs.unit_system must be SI")

    outputs = contract.get("outputs", {})
    if not outputs.get("_auto_generated", False):
        errors.append("outputs._auto_generated must be true")

    runtime = contract.get("runtime", {})
    timeout_seconds = runtime.get("timeout_seconds", 0)
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        errors.append("runtime.timeout_seconds must be positive int")

    return errors


def build_workflow_compliance_report(
    workflow_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """对工作流注册表生成 HOS 合规性报告。"""
    contracts: list[dict[str, Any]] = []
    for wf_name, spec in workflow_registry.items():
        contract = build_workflow_contract(wf_name, spec)
        errors = validate_workflow_contract(contract)
        contracts.append(
            {
                "workflow": wf_name,
                "module": spec.get("module", ""),
                "entry": spec.get("entry", ""),
                "valid": len(errors) == 0,
                "errors": errors,
                "contract": contract,
            }
        )

    passed = sum(1 for c in contracts if c["valid"])
    total = len(contracts)
    return {
        "hos_version": HOS_VERSION,
        "generated_at": _utc_now(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round((passed / total) if total else 0.0, 4),
        },
        "workflows": contracts,
    }


@dataclass
class VendorAdapterRegistry:
    """厂商适配器注册表（配置驱动，YAML 持久化）。"""

    registry_path: Path

    def load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"schema_version": "1.0", "vendors": {}}
        with self.registry_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"schema_version": "1.0", "vendors": {}}

    def save(self, data: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.registry_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def list_vendors(self) -> list[dict[str, Any]]:
        data = self.load()
        vendors = data.get("vendors", {})
        out: list[dict[str, Any]] = []
        for vendor_id, payload in vendors.items():
            out.append(
                {
                    "vendor_id": vendor_id,
                    "name": payload.get("name", vendor_id),
                    "status": payload.get("status", "active"),
                    "adapter_type": payload.get("adapter_type", "python"),
                    "workflow_count": len(payload.get("workflows", [])),
                    "updated_at": payload.get("updated_at"),
                }
            )
        return sorted(out, key=lambda x: x["vendor_id"])

    def register_vendor(self, manifest: dict[str, Any]) -> dict[str, Any]:
        for key in ["vendor_id", "name", "adapter_type"]:
            if not manifest.get(key):
                raise ValueError(f"manifest missing required field: {key}")
        if manifest.get("unit_system") and manifest.get("unit_system") != "SI":
            raise ValueError("vendor unit_system must be SI")

        vendor_id = str(manifest["vendor_id"]).strip()
        data = self.load()
        vendors = data.setdefault("vendors", {})

        current = vendors.get(vendor_id, {})
        merged = {
            **current,
            **manifest,
            "vendor_id": vendor_id,
            "updated_at": _utc_now(),
            "_auto_generated": True,
        }
        vendors[vendor_id] = merged
        self.save(data)
        return merged


def sanitize_for_json(value: Any) -> Any:
    """确保返回值可 JSON 序列化。"""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): sanitize_for_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_for_json(v) for v in value]
        if isinstance(value, tuple):
            return [sanitize_for_json(v) for v in value]
        return str(value)
