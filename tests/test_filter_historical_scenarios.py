import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from filter_historical_scenarios import filter_historical_scenarios

class TestFilterHistoricalScenarios(unittest.TestCase):
    @patch("filter_historical_scenarios.load_case_config")
    def test_filter_historical_scenarios_matches_data(self, mock_load):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "obs.sqlite"
            
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE observations (time TEXT, station TEXT, Z REAL, Q REAL)")
            conn.executemany(
                "INSERT INTO observations (time, station, Z, Q) VALUES (?, ?, ?, ?)",
                [
                    ("2021-07-01 10:00:00", "S1", 10.5, 100),
                    ("2021-07-02 10:00:00", "S1", 12.0, 200),
                    ("2021-07-03 10:00:00", "S2", 8.0, 50),
                ]
            )
            conn.commit()
            conn.close()
            
            mock_load.return_value = {
                "sqlite_paths": [str(db_path)],
                "knowledge": {
                    "scenarios": [
                        {
                            "id": "scenario_flood",
                            "start_time": "2021-07-01",
                            "end_time": "2021-07-02 23:59:59",
                            "station": "S1"
                        },
                        {
                            "id": "scenario_high_flow",
                            "variable": "Q",
                            "operator": ">",
                            "threshold": 150
                        },
                        {
                            "id": "scenario_no_match",
                            "variable": "Z",
                            "operator": ">",
                            "threshold": 20.0
                        }
                    ]
                }
            }
            
            # Monkeypatch the output dir creation so it doesn't write to actual workspace
            with patch("filter_historical_scenarios._WORKSPACE", Path(temp_dir)):
                res = filter_historical_scenarios("test_case")
            
            self.assertEqual(len(res), 2)
            self.assertEqual(res[0]["id"], "scenario_flood")
            self.assertEqual(res[0]["match_count"], 2)
            
            self.assertEqual(res[1]["id"], "scenario_high_flow")
            self.assertEqual(res[1]["match_count"], 1)

if __name__ == "__main__":
    unittest.main()
