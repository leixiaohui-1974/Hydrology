"""Specialized outcome extractor tests."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.outcome_contract import build_outcome_contract, validate_outcome_contract


class TestOutcomeSpecializedExtractors(unittest.TestCase):
    def test_section_analysis_prefers_result_assets_over_raw_sources(self) -> None:
        case_id = "ut_outcome_section_analysis"
        case_dir = ROOT_DIR.parent / "cases" / case_id
        contracts_dir = case_dir / "contracts"
        source_selection_dir = case_dir / "source_selection"
        product_outputs_dir = source_selection_dir / "product_outputs"
        raw_dir = ROOT_DIR.parent / "_tmp_outcome_raw" / case_id
        contracts_dir.mkdir(parents=True, exist_ok=True)
        product_outputs_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            (contracts_dir / "section_analysis.latest.json").write_text("{}", encoding="utf-8")
            (contracts_dir / "watershed_delineation_result.latest.json").write_text("{}", encoding="utf-8")
            (source_selection_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            (product_outputs_dir / "inspection.json").write_text("{}", encoding="utf-8")
            (raw_dir / "section.xlsx").write_text("raw", encoding="utf-8")

            contract = build_outcome_contract(
                workflow="section_analysis",
                case_id=case_id,
                result={
                    "n_sections_total": 673,
                    "evaluation": {
                        "n_stations": 6,
                        "overall_score": 0.875,
                        "grade": "A",
                        "warnings": ["240 个断面少于 5 个点"],
                        "recommendations": ["s4 需补充更深断面"],
                    },
                    "raw_source": f"_tmp_outcome_raw/{case_id}/section.xlsx",
                },
                status="completed",
                execution_profile="fast_validation",
            )

            self.assertEqual(validate_outcome_contract(contract), [])
            self.assertEqual(contract["artifacts"][0]["path"], f"cases/{case_id}/contracts/section_analysis.latest.json")
            self.assertIn(f"cases/{case_id}/source_selection/index.html", [item["path"] for item in contract["artifacts"]])
            self.assertNotIn(f"_tmp_outcome_raw/{case_id}/section.xlsx", [item["path"] for item in contract["artifacts"]])
            self.assertEqual(contract["metrics"]["overall_score"], 0.875)
            self.assertIn("断面质量等级 A", contract["dimensions"]["conclusion"][0]["value"])
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
            shutil.rmtree(raw_dir.parent, ignore_errors=True)

    def test_hyd_cal_binds_case_evidence_and_precision(self) -> None:
        case_id = "ut_outcome_hyd_cal"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        try:
            (contracts_dir / "hydraulic_calibration.latest.json").write_text(
                json.dumps({"summary": {"avg_val_nse": 0.91}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (contracts_dir / "D2_hydraulic_report.md").write_text("# D2 report", encoding="utf-8")

            contract = build_outcome_contract(
                workflow="hyd_cal",
                case_id=case_id,
                result={
                    "summary": {
                        "n_stations_calibrated": 4,
                        "avg_cal_nse": 0.94,
                        "avg_val_nse": 0.91,
                        "avg_cal_rmse": 0.12,
                    }
                },
                status="completed",
                execution_profile="fast_validation",
            )

            self.assertEqual(validate_outcome_contract(contract), [])
            self.assertEqual(contract["metrics"]["nse"], 0.91)
            self.assertEqual(contract["artifacts"][0]["path"], f"cases/{case_id}/contracts/hydraulic_calibration.latest.json")
            self.assertEqual(
                contract["dimensions"]["conclusion"][0]["evidence_path"],
                f"cases/{case_id}/contracts/hydraulic_calibration.latest.json",
            )
            self.assertIn("达到 0.85 阈值", contract["dimensions"]["conclusion"][0]["value"])
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)

    def test_d1d4_drops_existing_raw_source_when_case_results_exist(self) -> None:
        case_id = "ut_outcome_d1d4"
        case_dir = ROOT_DIR.parent / "cases" / case_id
        contracts_dir = case_dir / "contracts"
        raw_dir = ROOT_DIR.parent / "_tmp_outcome_raw" / case_id
        contracts_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            (contracts_dir / "d1d4_precision_report.latest.json").write_text("{}", encoding="utf-8")
            (raw_dir / "d1d4-source.xlsx").write_text("raw", encoding="utf-8")

            contract = build_outcome_contract(
                workflow="d1d4",
                case_id=case_id,
                result={
                    "capability_score": 4.6,
                    "wnal_score": 0.72,
                    "dimensions": {
                        "d1": {"score": 0.91, "level": "A"},
                    },
                    "raw_source": f"_tmp_outcome_raw/{case_id}/d1d4-source.xlsx",
                    "overall_problems": ["薄弱维度集中在 D4"],
                    "overall_recommendations": ["优先补强状态估计链路"],
                },
                status="completed",
                execution_profile="fast_validation",
            )

            artifact_paths = [item["path"] for item in contract["artifacts"]]
            self.assertEqual(artifact_paths[0], f"cases/{case_id}/contracts/d1d4_precision_report.latest.json")
            self.assertNotIn(f"_tmp_outcome_raw/{case_id}/d1d4-source.xlsx", artifact_paths)
            self.assertEqual(contract["dimensions"]["conclusion"][0]["evidence_path"], f"cases/{case_id}/contracts/d1d4_precision_report.latest.json")
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
            shutil.rmtree(raw_dir.parent, ignore_errors=True)

    def test_strict_revalidation_uses_summary_report_as_evidence(self) -> None:
        reports_dir = ROOT_DIR.parent / "reports" / "acceptance"
        summary_path = reports_dir / "strict_revalidation_summary.json"
        reports_dir.mkdir(parents=True, exist_ok=True)
        original_content = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
        try:
            summary_path.write_text(
                json.dumps(
                    {
                        "scenario_count": 6,
                        "modules": {
                            "physics": {
                                "failed_tests": 0,
                                "pass_rate": 1.0,
                                "average_score": 0.97,
                            },
                            "control": {
                                "failed_tests": 1,
                                "pass_rate": 0.83,
                                "average_score": 0.81,
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            contract = build_outcome_contract(
                workflow="strict_revalidation_ext",
                case_id="daduhe",
                result={"kind": "external_script", "returncode": 0},
                status="completed",
                execution_profile="fast_validation",
            )

            self.assertEqual(validate_outcome_contract(contract), [])
            self.assertAlmostEqual(contract["metrics"]["pass_rate"], 1.0)
            self.assertEqual(contract["artifacts"][0]["path"], "reports/acceptance/strict_revalidation_summary.json")
            self.assertEqual(
                contract["dimensions"]["recommendation"][0]["evidence_path"],
                "reports/acceptance/strict_revalidation_summary.json",
            )
            self.assertIn("failed_samples", contract["dimensions"]["recommendation"][0]["value"] or "strict_revalidation_summary.json")
        finally:
            if original_content is None:
                summary_path.unlink(missing_ok=True)
            else:
                summary_path.write_text(original_content, encoding="utf-8")

    def test_autonomy_autorun_binds_assessment_and_strict_review_assets(self) -> None:
        case_id = "ut_outcome_autonomy_autorun"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        reports_dir = ROOT_DIR.parent / "reports" / "acceptance"
        summary_path = reports_dir / "strict_revalidation_summary.json"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        original_content = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
        try:
            (contracts_dir / "autonomy_autorun.latest.json").write_text(
                json.dumps(
                    {
                        "final": {
                            "verdict": "PASS",
                            "overall_score": 0.86,
                            "stop_reason": "pass_reached",
                            "root_cause_hints": ["real_validation 时窗偏短"],
                        },
                        "rounds": [{"round": 1}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (contracts_dir / "autonomy_autorun.latest.md").write_text("# autorun", encoding="utf-8")
            (contracts_dir / "autonomy_assessment.latest.json").write_text(
                json.dumps(
                    {
                        "judge": {
                            "verdict": "PASS",
                            "weak_dimensions": [],
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (contracts_dir / "autonomy_assessment.latest.md").write_text("# assess", encoding="utf-8")
            (contracts_dir / "E2E_LIVE_DASHBOARD.html").write_text("<html>live</html>", encoding="utf-8")
            (contracts_dir / "E2E_LIVE_DASHBOARD.md").write_text("# live", encoding="utf-8")
            (contracts_dir / "outcome_coverage_report.latest.json").write_text("{}", encoding="utf-8")
            (contracts_dir / "e2e_outcome_verification_report.json").write_text("{}", encoding="utf-8")
            (contracts_dir / "e2e_outcome_verification_report.md").write_text("# verification", encoding="utf-8")
            summary_path.write_text(
                json.dumps(
                    {
                        "scenario_count": 12,
                        "modules": {
                            "physics": {"failed_tests": 1, "pass_rate": 0.95},
                            "control": {"failed_tests": 3, "pass_rate": 0.82},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            strict_payload = {
                "scenario_count": 12,
                "modules": {
                    "physics": {"failed_tests": 1, "pass_rate": 0.95},
                    "control": {"failed_tests": 3, "pass_rate": 0.82},
                },
            }

            def _patched_read_json(path_str: str):
                if path_str == "reports/acceptance/strict_revalidation_summary.json":
                    return strict_payload
                target = Path(path_str)
                if not target.is_absolute():
                    target = ROOT_DIR.parent / target
                return json.loads(target.read_text(encoding="utf-8"))

            with patch("workflows.outcome_contract._read_json_if_exists", side_effect=_patched_read_json):
                contract = build_outcome_contract(
                    workflow="autonomy_autorun",
                    case_id=case_id,
                    result={
                        "case_id": case_id,
                        "final_verdict": "PASS",
                        "final_score": 0.86,
                        "rounds": 1,
                        "json_report": str(contracts_dir / "autonomy_autorun.latest.json"),
                        "md_report": str(contracts_dir / "autonomy_autorun.latest.md"),
                    },
                    status="completed",
                    execution_profile="fast_validation",
                )

            self.assertEqual(validate_outcome_contract(contract), [])
            self.assertEqual(contract["artifacts"][0]["path"], f"cases/{case_id}/contracts/autonomy_autorun.latest.json")
            self.assertEqual(contract["dimensions"]["conclusion"][0]["evidence_path"], f"cases/{case_id}/contracts/autonomy_autorun.latest.json")
            self.assertEqual(contract["dimensions"]["recommendation"][0]["evidence_path"], f"cases/{case_id}/contracts/autonomy_assessment.latest.json")
            self.assertEqual(contract["dimensions"]["recommendation"][1]["evidence_path"], "reports/acceptance/strict_revalidation_summary.json")
            self.assertEqual(contract["dimensions"]["recommendation"][2]["label"], "启动/审查路径")
            self.assertIn(
                f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                contract["dimensions"]["recommendation"][2]["value"]["live_dashboard"],
            )
            self.assertIn(
                f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                contract["dimensions"]["recommendation"][2]["value"]["verification_assets"],
            )
            self.assertEqual(contract["dimensions"]["result"][0]["value"]["strict_review"]["failed_tests"], 4)
            self.assertIn(
                f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                [artifact["path"] for artifact in contract["artifacts"]],
            )
            self.assertIn(
                f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                [artifact["path"] for artifact in contract["artifacts"]],
            )
            self.assertIn(
                f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                [item["path"] for item in contract["slots"]["charts"]],
            )
            self.assertEqual(contract["metrics"]["overall_score"], 0.86)
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)
            if original_content is None:
                summary_path.unlink(missing_ok=True)
            else:
                summary_path.write_text(original_content, encoding="utf-8")

    def test_source_to_delineation_binds_workflow_topology_and_gis_assets(self) -> None:
        case_id = "ut_outcome_shidi_linkage"
        case_dir = ROOT_DIR.parent / "cases" / case_id
        contracts_dir = case_dir / "contracts"
        product_outputs_dir = case_dir / "source_selection" / "product_outputs"
        source_selection_dir = case_dir / "source_selection"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        product_outputs_dir.mkdir(parents=True, exist_ok=True)
        source_selection_dir.mkdir(parents=True, exist_ok=True)
        try:
            (contracts_dir / "pipeline_report.latest.json").write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "stage": "source_discovery",
                                "status": "completed",
                                "outputs": {
                                    "control_station_mapping": str(product_outputs_dir / "control_station_mapping.json"),
                                    "source_reliability": str(product_outputs_dir / "source_reliability.json"),
                                    "coordinate_validation": str(product_outputs_dir / "coordinate_validation.json"),
                                    "delineation_ready_json": str(product_outputs_dir / "outlets.delineation_ready.json"),
                                },
                            },
                            {
                                "stage": "data_pack_build",
                                "status": "completed",
                                "outputs": {
                                    "data_pack_json": str(contracts_dir / "data_pack.latest.json"),
                                },
                            },
                            {
                                "stage": "watershed_delineation",
                                "status": "completed",
                                "outputs": {
                                    "delineation_result_json": str(contracts_dir / "watershed_delineation_result.latest.json"),
                                },
                            },
                        ],
                        "summary": {"total_area_km2": 71748.4, "basins": [{"name": "石棉", "area_km2": 64316.1}]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (contracts_dir / "data_pack.latest.json").write_text("{}", encoding="utf-8")
            (contracts_dir / "watershed_delineation_result.latest.json").write_text(
                json.dumps({"total_area_km2": 71748.4, "basins": [{"name": "石棉"}, {"name": "瀑布沟"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (product_outputs_dir / "control_station_mapping.json").write_text(
                json.dumps({"mappings": [{"canonical_station_name": "石棉"}, {"canonical_station_name": "瀑布沟"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (product_outputs_dir / "outlets.delineation_ready.json").write_text(
                json.dumps({"count": 2, "outlets": [{"name": "石棉"}, {"name": "瀑布沟"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (product_outputs_dir / "source_reliability.json").write_text("{}", encoding="utf-8")
            (product_outputs_dir / "coordinate_validation.json").write_text(
                json.dumps({"anomaly_count": 1}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (source_selection_dir / "index.html").write_text("<html></html>", encoding="utf-8")

            contract = build_outcome_contract(
                workflow="source_to_delineation",
                case_id=case_id,
                result={"kind": "external_script", "returncode": 0},
                status="completed",
                execution_profile="fast_validation",
            )

            self.assertEqual(validate_outcome_contract(contract), [])
            artifact_paths = [item["path"] for item in contract["artifacts"]]
            self.assertEqual(artifact_paths[0], f"cases/{case_id}/contracts/pipeline_report.latest.json")
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/control_station_mapping.json", artifact_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/outlets.delineation_ready.json", artifact_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/source_reliability.json", artifact_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/coordinate_validation.json", artifact_paths)
            self.assertIn(f"cases/{case_id}/contracts/watershed_delineation_result.latest.json", artifact_paths)

            topology_paths = [item["path"] for item in contract["slots"]["topology"]]
            gis_paths = [item["path"] for item in contract["slots"]["gis"]]
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/control_station_mapping.json", topology_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/outlets.delineation_ready.json", topology_paths)
            self.assertIn(f"cases/{case_id}/contracts/watershed_delineation_result.latest.json", topology_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/source_reliability.json", gis_paths)
            self.assertIn(f"cases/{case_id}/source_selection/product_outputs/coordinate_validation.json", gis_paths)

            summary = contract["dimensions"]["result"][0]["value"]
            self.assertEqual(summary["mapped_stations"], 2)
            self.assertEqual(summary["ready_outlets"], 2)
            self.assertEqual(summary["basin_count"], 2)
            self.assertEqual(summary["coordinate_anomaly_count"], 1)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
