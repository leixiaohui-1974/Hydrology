"""Tests for examples/build_release_manifest.py."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "examples" / "build_release_manifest.py"


class TestBuildReleaseManifestScript(unittest.TestCase):
    def test_script_preserves_explicit_parameter_governance_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            workflow_run_path = tmpdir_path / "workflow_run.json"
            review_bundle_path = tmpdir_path / "review_bundle.json"
            output_path = tmpdir_path / "release_manifest.json"
            extra_artifact = "cases/daduhe/contracts/parameter_governance.latest.json"

            workflow_run_path.write_text(
                json.dumps(
                    {
                        "run_id": "run-001",
                        "case_id": "daduhe",
                        "workflow_type": "watershed_delineation",
                        "status": "completed",
                        "inputs": [],
                        "outputs": [],
                        "steps": [],
                        "metadata": {},
                        "schema_version": "0.1.0",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            review_bundle_path.write_text(
                json.dumps(
                    {
                        "review_id": "review-001",
                        "run_id": "run-001",
                        "case_id": "daduhe",
                        "verdict": "pass_with_comments",
                        "findings": [],
                        "report_artifacts": [],
                        "metadata": {},
                        "schema_version": "0.1.0",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--case-id",
                    "daduhe",
                    "--version",
                    "v1.0.0",
                    "--workflow-run",
                    str(workflow_run_path),
                    "--review-bundle",
                    str(review_bundle_path),
                    "--output",
                    str(output_path),
                    "--artifact",
                    extra_artifact,
                ],
                check=True,
                cwd=str(ROOT_DIR),
            )

            saved = json.loads(output_path.read_text(encoding="utf-8"))
            assert extra_artifact in [item["path"] for item in saved["artifacts"]]
            assert saved.get("governance_gates", {}).get("index_rel") == "Hydrology/configs/platform_governance_gates.index.json"

    def test_script_builds_release_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            workflow_run_path = tmpdir_path / "workflow_run.json"
            review_bundle_path = tmpdir_path / "review_bundle.json"

            workflow_run_path.write_text(
                json.dumps(
                    {
                        "run_id": "run-001",
                        "case_id": "daduhe",
                        "workflow_type": "hydrology_full_pipeline",
                        "status": "completed",
                        "inputs": [],
                        "outputs": [],
                        "steps": [],
                        "started_at": "2026-03-30T00:00:00",
                        "completed_at": "2026-03-30T01:00:00",
                        "metadata": {},
                        "schema_version": "0.1.0",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            review_bundle_path.write_text(
                json.dumps(
                    {
                        "review_id": "review-001",
                        "run_id": "run-001",
                        "case_id": "daduhe",
                        "verdict": "pass_with_comments",
                        "findings": [],
                        "report_artifacts": [
                            {
                                "artifact_id": "review-001:report",
                                "artifact_type": "html_report",
                                "path": str(tmpdir_path / "report.html"),
                                "metadata": {"role": "acceptance_report"},
                            }
                        ],
                        "metadata": {},
                        "schema_version": "0.1.0",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            output_path = tmpdir_path / "release_manifest.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--case-id",
                    "daduhe",
                    "--version",
                    "v1.0.0",
                    "--workflow-run",
                    str(workflow_run_path),
                    "--review-bundle",
                    str(review_bundle_path),
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=str(ROOT_DIR),
            )

            self.assertIn("Release manifest:", result.stdout)
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["included_runs"], ["run-001"])
            self.assertEqual(saved["review_refs"], ["review-001"])
            self.assertIn("governance_gates", saved)
            self.assertEqual(
                saved["governance_gates"].get("index_rel"),
                "Hydrology/configs/platform_governance_gates.index.json",
            )

    def test_script_collects_autonomy_release_ready_artifacts(self):
        case_id = "ut_release_manifest_autonomy_path"
        contracts_dir = ROOT_DIR.parent / "cases" / case_id / "contracts"
        reports_dir = ROOT_DIR.parent / "reports" / "acceptance"
        summary_path = reports_dir / "strict_revalidation_summary.json"
        original_summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
        contracts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in {
            "autonomy_autorun.latest.md": "# autorun",
            "autonomy_assessment.latest.json": "{}",
            "autonomy_assessment.latest.md": "# assess",
            "E2E_LIVE_DASHBOARD.html": "<html>live</html>",
            "E2E_LIVE_DASHBOARD.md": "# live",
            "outcome_coverage_report.latest.json": "{}",
            "e2e_outcome_verification_report.json": "{}",
            "e2e_outcome_verification_report.md": "# verification",
        }.items():
            (contracts_dir / rel_path).write_text(content, encoding="utf-8")
        (contracts_dir / "autonomy_autorun.latest.json").write_text(
            json.dumps(
                {
                    "launch_review_path": {
                        "strict_revalidation_summary": "reports/acceptance/strict_revalidation_summary.json",
                        "live_dashboard": [
                            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
                        ],
                        "verification_assets": [
                            f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
                            f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                            f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
                        ],
                        "review_sequence": [
                            "reports/acceptance/strict_revalidation_summary.json",
                            f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                            f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                        ],
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path.write_text("{}", encoding="utf-8")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                workflow_run_path = tmpdir_path / "workflow_run.json"
                review_bundle_path = tmpdir_path / "review_bundle.json"
                output_path = tmpdir_path / "release_manifest.json"

                workflow_run_path.write_text(
                    json.dumps(
                        {
                            "run_id": "run-001",
                            "case_id": case_id,
                            "workflow_type": "hydrology_full_pipeline",
                            "status": "completed",
                            "inputs": [],
                            "outputs": [],
                            "steps": [],
                            "started_at": "2026-03-30T00:00:00",
                            "completed_at": "2026-03-30T01:00:00",
                            "metadata": {},
                            "schema_version": "0.1.0",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                review_bundle_path.write_text(
                    json.dumps(
                        {
                            "review_id": "review-001",
                            "run_id": "run-001",
                            "case_id": case_id,
                            "verdict": "pass_with_comments",
                            "findings": [],
                            "report_artifacts": [],
                            "metadata": {},
                            "schema_version": "0.1.0",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_PATH),
                        "--case-id",
                        case_id,
                        "--version",
                        "v1.0.0",
                        "--workflow-run",
                        str(workflow_run_path),
                        "--review-bundle",
                        str(review_bundle_path),
                        "--output",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(ROOT_DIR),
                )

                saved = json.loads(output_path.read_text(encoding="utf-8"))
                artifact_paths = [item["path"] for item in saved["artifacts"]]
                self.assertIn(f"cases/{case_id}/contracts/autonomy_autorun.latest.json", artifact_paths)
                self.assertIn("reports/acceptance/strict_revalidation_summary.json", artifact_paths)
                self.assertIn(f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html", artifact_paths)
                self.assertIn(f"cases/{case_id}/contracts/e2e_outcome_verification_report.json", artifact_paths)
                self.assertIn("governance_gates", saved)
                self.assertEqual(
                    saved["metadata"]["release_ready_path"],
                    [
                        f"cases/{case_id}/contracts/autonomy_autorun.latest.json",
                        f"cases/{case_id}/contracts/autonomy_autorun.latest.md",
                        f"cases/{case_id}/contracts/autonomy_assessment.latest.json",
                        f"cases/{case_id}/contracts/autonomy_assessment.latest.md",
                        "reports/acceptance/strict_revalidation_summary.json",
                        f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.html",
                        f"cases/{case_id}/contracts/E2E_LIVE_DASHBOARD.md",
                        f"cases/{case_id}/contracts/outcome_coverage_report.latest.json",
                        f"cases/{case_id}/contracts/e2e_outcome_verification_report.json",
                        f"cases/{case_id}/contracts/e2e_outcome_verification_report.md",
                    ],
                )
        finally:
            shutil.rmtree(contracts_dir.parent, ignore_errors=True)
            if original_summary is None:
                summary_path.unlink(missing_ok=True)
            else:
                summary_path.write_text(original_summary, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
