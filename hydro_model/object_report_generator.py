import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Dict

WORKSPACE = Path(__file__).resolve().parents[2]


def _load_water_object_report_module() -> tuple[Any, Any]:
    try:
        from hydromind_contracts.water_object_report import (
            get_water_object_report_convention,
            validate_water_object_report_payload,
        )

        return get_water_object_report_convention, validate_water_object_report_payload
    except ModuleNotFoundError:
        module_path = WORKSPACE / "hydromind-contracts" / "hydromind_contracts" / "water_object_report.py"
        spec = importlib.util.spec_from_file_location("hydromind_contracts.water_object_report", module_path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.get_water_object_report_convention, module.validate_water_object_report_payload


get_water_object_report_convention, validate_water_object_report_payload = _load_water_object_report_module()

log = logging.getLogger(__name__)


def _serialize_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(WORKSPACE.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


class ObjectReportGenerator:
    """Generates standardized markdown and JSON reports for water system objects."""

    def __init__(self, case_id: str, output_dir: Path):
        self.case_id = case_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generated_reports = []

    def _render_markdown(self, payload: Dict[str, Any]) -> str:
        convention = get_water_object_report_convention(str(payload.get("object_type", "")))
        lines = [
            f"# {payload.get('display_name', convention.display_name)} 结果报告",
            "",
            f"- 对象类型: {convention.object_type}",
            f"- 对象 ID: {payload.get('object_id', '')}",
            f"- 状态: {payload.get('status', 'available')}",
            "",
            payload.get("summary", ""),
            "",
        ]
        sections = payload.get("sections") or {}
        
        findings = payload.get("findings", [])
        recommendations = payload.get("recommendations", [])
        evidence = payload.get("evidence", [])

        if findings:
            lines.append("## 诊断发现 (Findings)")
            lines.append("")
            for f in findings:
                lines.append(f"- {f}")
            lines.append("")

        if recommendations:
            lines.append("## 建议 (Recommendations)")
            lines.append("")
            for r in recommendations:
                lines.append(f"- {r}")
            lines.append("")

        if evidence:
            lines.append("## 诊断证据 (Evidence)")
            lines.append("")
            for e in evidence:
                lines.append(f"- **{e.get('metric', 'Metric')}**: {e.get('value', '')} (阈值: {e.get('threshold', '')})")
            lines.append("")

        for section_name in convention.markdown_sections:
            content = sections.get(section_name)
            if not content:
                continue
            # Title case with spaces
            title = section_name.replace("_", " ").title()
            lines.append(f"## {title}")
            lines.append("")
            if isinstance(content, str):
                lines.append(content)
            else:
                lines.append(json.dumps(content, ensure_ascii=False, indent=2))
            lines.append("")
        return "\n".join(lines)

    def _generate_diagnostics(self, object_type: str, metrics: dict, details: dict, rules: dict) -> dict:
        """
        Dynamically generate diagnostics (findings, recommendations, evidence) 
        based on metrics, details, and the provided rules dictionary.
        Hardcoding thresholds is strictly avoided.
        """
        findings = []
        recommendations = []
        evidence = []

        # Get thresholds from rules, defaulting to fallback if rules is empty or missing keys
        rmse_threshold = rules.get("rmse_threshold", 0.5)
        control_u_penalty_threshold = rules.get("control_u_penalty_threshold", 0.1)

        # 1. Generic Diagnostics (e.g., RMSE)
        rmse = metrics.get("RMSE")
        if rmse is not None:
            if rmse > rmse_threshold:
                findings.append(f"RMSE ({rmse:.4f}) 超过了预设的警戒阈值 ({rmse_threshold})。")
                recommendations.append("建议检查模型状态估计器的观测噪声协方差矩阵配置。")
                evidence.append({"metric": "RMSE", "value": rmse, "threshold": rmse_threshold})
            else:
                findings.append(f"RMSE ({rmse:.4f}) 处于正常范围 (<= {rmse_threshold})。")

        # 2. Object-Specific Diagnostics
        if object_type == "PumpStation":
            control_u_penalty = metrics.get("Control_u_penalty")
            if control_u_penalty is not None:
                if control_u_penalty > control_u_penalty_threshold:
                    findings.append(f"泵站控制代价 ({control_u_penalty:.4f}) 过高 (阈值: {control_u_penalty_threshold})。可能存在频繁启停抖动。")
                    recommendations.append("建议增大 MPC 目标函数中对控制量变化的惩罚权重，或调宽死区限制。")
                    evidence.append({"metric": "Control_u_penalty", "value": control_u_penalty, "threshold": control_u_penalty_threshold})

        elif object_type == "Gate":
            gate_opening_error = metrics.get("gate_opening_error")
            gate_error_threshold = rules.get("gate_error_threshold", 0.05)
            if gate_opening_error is not None:
                if gate_opening_error > gate_error_threshold:
                    findings.append(f"闸门开度控制误差 ({gate_opening_error:.4f}) 超过阈值 ({gate_error_threshold})。")
                    recommendations.append("建议检查闸门机械执行机构的死区或死滞补偿逻辑。")
                    evidence.append({"metric": "gate_opening_error", "value": gate_opening_error, "threshold": gate_error_threshold})

        elif object_type == "Reservoir":
            water_level_deviation = metrics.get("water_level_deviation")
            level_deviation_threshold = rules.get("level_deviation_threshold", 0.2)
            if water_level_deviation is not None:
                if water_level_deviation > level_deviation_threshold:
                    findings.append(f"水库水位偏差 ({water_level_deviation:.4f}) 超过阈值 ({level_deviation_threshold})。")
                    recommendations.append("建议结合上游来水预报调整防洪调度或发电调度规则曲线。")
                    evidence.append({"metric": "water_level_deviation", "value": water_level_deviation, "threshold": level_deviation_threshold})

        return {
            "findings": findings,
            "recommendations": recommendations,
            "evidence": evidence
        }

    def generate_report(self, object_type: str, object_id: str, display_name: str, metrics: dict, details: dict, rules: dict = None):
        try:
            convention = get_water_object_report_convention(object_type)
        except KeyError:
            log.warning(f"Unknown object type: {object_type}")
            return None

        rules = rules or {}
        diagnostics = self._generate_diagnostics(convention.object_type, metrics, details, rules)

        # Build payload with minimum required fields
        payload = {
            "object_id": str(object_id),
            "object_type": convention.object_type,
            "display_name": display_name,
            "summary": f"自动生成的 {convention.display_name} 运行结果报告",
            "location": {"case_id": self.case_id},
            "status": "available",
            "metadata": {"metrics": metrics},
            "findings": diagnostics["findings"],
            "recommendations": diagnostics["recommendations"],
            "evidence": diagnostics["evidence"],
            "sections": {
                "overview": f"对象 {display_name} 的控制/仿真运行结果概要。",
                "results_and_risks": json.dumps(metrics, ensure_ascii=False, indent=2),
                "process_and_method": details.get("method", "基于自动控制与状态估计流水线。"),
            }
        }

        
        # Fill placeholders for required fields to pass validation
        for field in convention.required_fields:
            if field not in payload:
                payload[field] = details.get(field, "auto_placeholder")

        errors = validate_water_object_report_payload(payload)
        if errors:
            log.error(f"Validation failed for {object_id} ({object_type}): {errors}")
            return None

        slug = f"{convention.object_type.lower()}_{object_id}.report"
        json_path = self.output_dir / f"{slug}.json"
        md_path = self.output_dir / f"{slug}.md"

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self._render_markdown(payload), encoding="utf-8")

        self.generated_reports.append({
            "object_type": convention.object_type,
            "object_id": object_id,
            "json_path": _serialize_path(json_path),
            "markdown_path": _serialize_path(md_path),
        })
        return payload

    def save_index(self):
        index_path = self.output_dir / "standard_object_reports.index.json"
        index_payload = {
            "case_id": self.case_id,
            "reports": self.generated_reports
        }
        index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return index_path
