import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import export_case_data_intelligence

class TestExportCaseDataIntelligenceAdvancedLearning(unittest.TestCase):
    @patch("export_case_data_intelligence.load_case_config")
    @patch("export_case_data_intelligence.load_case_manifest")
    @patch("export_case_data_intelligence._load_control_payload")
    @patch("export_case_data_intelligence._load_source_bundle")
    @patch("export_case_data_intelligence._load_source_import_session")
    def test_recommends_advanced_learning_when_scada_and_scenarios_present(
        self, mock_import_session, mock_bundle, mock_control, mock_manifest, mock_config
    ):
        mock_config.return_value = {
            "project_type": "canal",
            "data_sources": {
                "scada": {
                    "database": {"path": "cases/test_case/data/obs.sqlite"}
                }
            }
        }
        mock_manifest.return_value = (Path("test"), {})
        mock_control.return_value = ({}, {})
        mock_bundle.return_value = {}
        mock_import_session.return_value = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            
            # Setup filtered scenarios
            contracts_dir = workspace / "cases" / "test_case" / "contracts"
            contracts_dir.mkdir(parents=True)
            scenarios_file = contracts_dir / "filtered_historical_scenarios.latest.json"
            scenarios_file.write_text(json.dumps([{"id": "scenario_1", "match_count": 10}]), encoding="utf-8")
            
            # Monkeypatch _WORKSPACE so it finds the filtered scenarios
            with patch("export_case_data_intelligence._WORKSPACE", workspace):
                profile = export_case_data_intelligence.build_case_data_profile("test_case")
                
                strategy = profile["learning_strategy"]
                self.assertIn("data_assimilation", strategy)
                self.assertIn("state_estimation", strategy)
                self.assertIn("parameter_estimation", strategy)
                
                self.assertEqual(strategy["data_assimilation"]["status"], "ready")
                self.assertEqual(strategy["state_estimation"]["status"], "ready")
                self.assertEqual(strategy["parameter_estimation"]["status"], "ready")
                self.assertEqual(strategy["parameter_learning"]["status"], "ready")

    @patch("export_case_data_intelligence.load_case_config")
    @patch("export_case_data_intelligence.load_case_manifest")
    @patch("export_case_data_intelligence._load_control_payload")
    @patch("export_case_data_intelligence._load_source_bundle")
    @patch("export_case_data_intelligence._load_source_import_session")
    def test_defers_advanced_learning_when_scenarios_missing(
        self, mock_import_session, mock_bundle, mock_control, mock_manifest, mock_config
    ):
        mock_config.return_value = {
            "project_type": "canal",
            "data_sources": {
                "scada": {
                    "database": {"path": "cases/test_case/data/obs.sqlite"}
                }
            }
        }
        mock_manifest.return_value = (Path("test"), {})
        mock_control.return_value = ({}, {})
        mock_bundle.return_value = {}
        mock_import_session.return_value = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            
            # Do NOT create filtered scenarios file
            with patch("export_case_data_intelligence._WORKSPACE", workspace):
                profile = export_case_data_intelligence.build_case_data_profile("test_case")
                
                strategy = profile["learning_strategy"]
                
                self.assertEqual(strategy["data_assimilation"]["status"], "deferred")
                self.assertEqual(strategy["state_estimation"]["status"], "deferred")
                self.assertEqual(strategy["parameter_estimation"]["status"], "deferred")

if __name__ == "__main__":
    unittest.main()
