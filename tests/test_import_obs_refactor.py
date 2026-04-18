import sys
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch
import tempfile
import json

WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"

if str(HYDROLOGY) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY))

from scripts.import_observation_csv_to_sqlite import import_observation_csv_to_sqlite, _init_db
from workflows.scada_replay_engine import ScadaReplayEngine, ReplayConfig

class TestObservationRefactor(unittest.TestCase):
    @patch('scripts.import_observation_csv_to_sqlite.load_case_config')
    def test_import_uses_yaml_config_and_writes_to_observations(self, mock_load_case_config):
        mock_load_case_config.return_value = {
            "knowledge": {
                "scada_timeseries": {
                    "csv_extraction_rules": {
                        "observed_flow": {"variable": "Q", "unit": "m3/s", "time_step": "1min"},
                        "observed_water_level": {"variable": "Z", "unit": "m", "time_step": "1min"},
                    }
                }
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sqlite_path = temp_path / "test.sqlite"
            csv_path = temp_path / "test_obs.csv"
            
            # Create a mock CSV
            csv_path.write_text("time,station_id,variable,value\n2021-07-10 12:00:00,station_1,flow,15.5\n2021-07-10 12:00:00,station_1,water_level,2.3\n")
            
            # Run the import
            result = import_observation_csv_to_sqlite(
                case_id="test_case",
                csv_path=csv_path,
                sqlite_path=sqlite_path,
                replace=True
            )
            
            self.assertTrue(result["ok"])
            
            # Verify data in observations table
            conn = sqlite3.connect(sqlite_path)
            cursor = conn.cursor()
            
            # Check table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='observations'")
            self.assertIsNotNone(cursor.fetchone())
            
            # Check data was mapped correctly based on YAML rules
            cursor.execute("SELECT station, time, Q, Z FROM observations")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "station_1")
            self.assertEqual(rows[0][1], "2021-07-10 12:00:00")
            self.assertEqual(rows[0][2], 15.5) # Q mapped from flow
            self.assertEqual(rows[0][3], 2.3)  # Z mapped from water_level
            conn.close()
            
    def test_scada_replay_engine_reads_from_observations(self):
        conn = sqlite3.connect(':memory:')
        _init_db(conn)
        # Insert a test observation
        conn.execute(
            "INSERT INTO observations (name, station, time, Z, Q) VALUES (?, ?, ?, ?, ?)",
            ("Station 1", "station_1", "2021-07-10 12:00:00", 2.3, 15.5)
        )
        
        cfg = ReplayConfig(
            case_id="test_case",
            sqlite_path=Path(':memory:'),
            scenario_id="scenario_1",
            replay_speed=1.0,
            quality_code="GOOD",
            max_events=100,
            query_start="2021-07-10 00:00:00",
            query_end="2021-07-11 00:00:00"
        )
        
        engine = ScadaReplayEngine(cfg)
        rows = engine._query_observations_table(conn)
        
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["station_id"], "station_1")
        self.assertEqual(rows[0]["station_name"], "Station 1")
        self.assertEqual(rows[0]["ts_event"], "2021-07-10 12:00:00")
        self.assertEqual(rows[0]["Z"], 2.3)
        self.assertEqual(rows[0]["Q"], 15.5)
        
        conn.close()

if __name__ == '__main__':
    unittest.main()
