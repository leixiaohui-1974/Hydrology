from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ParameterDefinition:
    parameter_id: str
    stage: str
    category: str
    physical_meaning: str
    unit: str
    default_value: float | int | str | None
    bounds: tuple[float, float] | None
    source_of_truth: str
    sensitivity_enabled: bool
    calibration_enabled: bool
    assimilation_enabled: bool
    error_model_role: str = "none"
    dependencies: list[str] = field(default_factory=list)
    validation_metric_links: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bounds"] = list(self.bounds) if self.bounds is not None else None
        return payload


@dataclass
class StageGovernanceArtifact:
    case_id: str
    stage: str
    parameters: list[ParameterDefinition]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "parameters": [item.to_dict() for item in self.parameters],
            "metadata": self.metadata,
        }



def screen_parameters(parameters: list[ParameterDefinition]) -> list[ParameterDefinition]:
    screened: list[ParameterDefinition] = []
    for item in parameters:
        if not item.sensitivity_enabled:
            continue
        if item.category == "configuration":
            continue
        screened.append(item)
    return screened



def analyze_local_sensitivity(
    baseline: dict[str, float],
    evaluator: Callable[[dict[str, float]], float],
    perturbation: float = 0.05,
) -> list[dict[str, Any]]:
    baseline_score = float(evaluator(dict(baseline)))
    findings: list[dict[str, Any]] = []
    for parameter_id, baseline_value in baseline.items():
        if not isinstance(baseline_value, (int, float)):
            continue
        delta = baseline_value * perturbation if baseline_value != 0 else perturbation
        candidate = dict(baseline)
        candidate[parameter_id] = baseline_value + delta
        perturbed_score = float(evaluator(candidate))
        findings.append(
            {
                "parameter_id": parameter_id,
                "score": abs(perturbed_score - baseline_score),
                "directionality": "increase" if perturbed_score >= baseline_score else "decrease",
                "physics_risk_flag": False,
                "recommended_action": "calibrate",
            }
        )
    return sorted(findings, key=lambda item: item["score"], reverse=True)



def freeze_candidate_set(findings: list[dict[str, Any]], primary_limit: int = 5) -> dict[str, list[str]]:
    primary: list[str] = []
    secondary: list[str] = []
    forbidden: list[str] = []
    for finding in findings:
        if finding.get("physics_risk_flag"):
            forbidden.append(finding["parameter_id"])
        elif len(primary) < primary_limit:
            primary.append(finding["parameter_id"])
        else:
            secondary.append(finding["parameter_id"])
    return {
        "primary_candidates": primary,
        "secondary_candidates": secondary,
        "forbidden_candidates": forbidden,
    }



def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
