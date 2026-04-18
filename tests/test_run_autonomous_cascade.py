from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflows.run_autonomous_cascade import run_autonomous, stage_control, stage_dispatch


def _paths(tmp_path: Path) -> dict[str, Path]:
    contracts = tmp_path / "cases" / "demo" / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    return {
        "case_dir": contracts.parent,
        "contracts": contracts,
        "config": tmp_path / "Hydrology" / "configs" / "demo.yaml",
        "product_outputs": contracts.parent / "source_selection" / "product_outputs",
    }


def test_stage_dispatch_marks_error_on_state_estimation_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    commands: list[list[str]] = []

    def fake_run_command(argv: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
        commands.append(argv)
        if "run_state_estimation.py" in argv[1]:
            return {"argv": argv, "returncode": 1, "stdout_tail": "", "stderr_tail": "boom"}
        return {"argv": argv, "returncode": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr("workflows.run_autonomous_cascade._run_command", fake_run_command)

    result = stage_dispatch("demo", paths)

    assert result["status"] == "error"
    assert result["reason"] == "boom"
    assert any("run_state_estimation.py" in argv[1] for argv in commands)


def test_stage_dispatch_propagates_state_estimation_quality_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    (paths["contracts"] / "state_estimation.latest.json").write_text(
        json.dumps(
            {
                "outcome_status": "quality_failed",
                "quality_gate_passed": False,
                "quality_reason": "状态估计整体质量未达标",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_run_command(argv: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
        return {"argv": argv, "returncode": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr("workflows.run_autonomous_cascade._run_command", fake_run_command)

    result = stage_dispatch("demo", paths)

    assert result["status"] == "quality_failed"
    assert result["reason"] == "状态估计整体质量未达标"


def test_stage_control_marks_error_on_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    script_path = tmp_path / "E2EControl" / "scripts" / "run_strict_revalidation.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr("workflows.run_autonomous_cascade.WORKSPACE", tmp_path)

    def fake_run_command(argv: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
        return {"argv": argv, "returncode": 2, "stdout_tail": "", "stderr_tail": "hf failed"}

    monkeypatch.setattr("workflows.run_autonomous_cascade._run_command", fake_run_command)

    result = stage_control("demo", paths)

    assert result["status"] == "error"
    assert result["reason"] == "hf failed"


def test_stage_control_reads_quality_failed_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    script_path = tmp_path / "E2EControl" / "scripts" / "run_strict_revalidation.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr("workflows.run_autonomous_cascade.WORKSPACE", tmp_path)

    def fake_run_command(argv: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
        output_path = None
        if "--output" in argv:
            output_path = Path(argv[argv.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "scenario_count": 4,
                        "modules": {
                            "physics": {"pass_rate": 0.6},
                            "control": {"pass_rate": 0.5},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        elif "run_realtime_control.py" in argv[1]:
            (paths["contracts"] / "realtime_control_result.latest.json").write_text(
                json.dumps({"status": "executed"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return {"argv": argv, "returncode": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr("workflows.run_autonomous_cascade._run_command", fake_run_command)

    result = stage_control("demo", paths)

    assert result["status"] == "quality_failed"
    assert "控制总体通过率未达标" in str(result["reason"])


def test_run_autonomous_returns_degraded_when_any_step_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contracts = tmp_path / "cases" / "demo" / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "workflows.run_autonomous_cascade._resolve_paths",
        lambda case_id: {
            "case_dir": contracts.parent,
            "contracts": contracts,
            "config": tmp_path / "Hydrology" / "configs" / f"{case_id}.yaml",
            "product_outputs": contracts.parent / "source_selection" / "product_outputs",
        },
    )
    monkeypatch.setattr(
        "workflows.run_autonomous_cascade.STAGE_FUNCS",
        {
            "dispatch": lambda case_id, paths: {"stage": "dispatch", "status": "completed"},
            "control": lambda case_id, paths: {"stage": "control", "status": "degraded", "reason": "质量降级"},
        },
    )

    report = run_autonomous("demo", ["dispatch", "control"])

    assert report["status"] == "degraded"
    assert report["outcome_status"] == "degraded"
    assert report["quality_gate_passed"] is False
    assert "control" in str(report["quality_reason"])


def test_run_autonomous_returns_quality_failed_when_any_step_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contracts = tmp_path / "cases" / "demo" / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "workflows.run_autonomous_cascade._resolve_paths",
        lambda case_id: {
            "case_dir": contracts.parent,
            "contracts": contracts,
            "config": tmp_path / "Hydrology" / "configs" / f"{case_id}.yaml",
            "product_outputs": contracts.parent / "source_selection" / "product_outputs",
        },
    )
    monkeypatch.setattr(
        "workflows.run_autonomous_cascade.STAGE_FUNCS",
        {
            "dispatch": lambda case_id, paths: {"stage": "dispatch", "status": "completed"},
            "control": lambda case_id, paths: {"stage": "control", "status": "error", "reason": "脚本失败"},
        },
    )

    report = run_autonomous("demo", ["dispatch", "control"])

    assert report["status"] == "quality_failed"
    assert report["outcome_status"] == "quality_failed"
    assert report["quality_gate_passed"] is False
    assert "control" in str(report["quality_reason"])
