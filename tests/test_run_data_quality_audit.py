from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows import run_data_quality_audit as audit


def _workspace_rel(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


class TestRunDataQualityAudit(unittest.TestCase):
    def _create_demo_db(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE stations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    station_type TEXT,
                    lat REAL,
                    lon REAL,
                    elevation REAL,
                    basin_area_km2 REAL,
                    source TEXT,
                    metadata_json TEXT
                );
                CREATE TABLE timeseries (
                    station_id TEXT NOT NULL,
                    variable TEXT NOT NULL,
                    time_step TEXT NOT NULL,
                    time TEXT NOT NULL,
                    value REAL,
                    quality INTEGER,
                    PRIMARY KEY (station_id, variable, time_step, time)
                );
                """
            )
            conn.execute(
                """
                INSERT INTO stations (id, name, station_type, source, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "24001201",
                    "取水口",
                    "open_channel",
                    "station_meta.csv",
                    json.dumps({"normal_pool_m": 348.0, "dead_pool_m": 346.0}, ensure_ascii=False),
                ),
            )
            conn.executemany(
                """
                INSERT INTO timeseries (station_id, variable, time_step, time, value, quality)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    ("24001201", "water_level", "1min", "2025-07-01 00:00:00", 347.34, 1),
                    ("24001201", "water_level", "1min", "2025-07-01 00:01:00", 347.35, 1),
                    ("24001201", "flow", "1min", "2025-07-01 00:00:00", 3.20, 1),
                    ("24001201", "flow", "1min", "2025-07-01 00:01:00", 3.26, 1),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def _create_schema_poor_db(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE misc (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO misc (name) VALUES ('placeholder')")
            conn.commit()
        finally:
            conn.close()

    def _create_observations_db(self, db_path: Path, *, include_z: bool = True, include_q: bool = True) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        columns = ["station TEXT", "time TEXT"]
        if include_z:
            columns.append("Z REAL")
        if include_q:
            columns.append("Q REAL")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(f"CREATE TABLE observations ({', '.join(columns)})")
            insert_columns = ["station", "time"]
            if include_z:
                insert_columns.append("Z")
            if include_q:
                insert_columns.append("Q")
            values = ["S-001", "2026-01-01T00:00:00"]
            if include_z:
                values.append(123.4)
            if include_q:
                values.append(56.7)
            placeholders = ", ".join("?" for _ in insert_columns)
            conn.execute(
                f"INSERT INTO observations ({', '.join(insert_columns)}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    def _run_audit(self, workspace: Path, cfg: dict[str, object]) -> dict[str, object]:
        original_workspace = audit.WORKSPACE
        original_load_case_config = audit.load_case_config
        try:
            audit.WORKSPACE = workspace
            audit.load_case_config = lambda case_id, config_path=None: {
                "case_id": case_id,
                **cfg,
            }
            return audit.run_audit("demo_case")
        finally:
            audit.WORKSPACE = original_workspace
            audit.load_case_config = original_load_case_config

    def test_run_audit_accepts_explicit_sqlite_without_hydromind_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "observations.sqlite"
            self._create_demo_db(db_path)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(db_path.resolve()))
            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["tables"]["stations"]["row_count"], 1)
            self.assertEqual(report["tables"]["timeseries"]["row_count"], 4)
            self.assertIn("24001201", report["station_audit"])
            self.assertIn("water_level", report["station_audit"]["24001201"]["variables"])
            self.assertIn("flow", report["station_audit"]["24001201"]["variables"])
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit.latest.json").is_file())
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit_report.md").is_file())

    def test_run_audit_ignores_non_sqlite_entries_in_sqlite_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "observations.sqlite"
            self._create_demo_db(db_path)
            invalid_xlsx = workspace / "cases" / "demo_case" / "raw" / "stations.xlsx"
            invalid_zip = workspace / "cases" / "demo_case" / "raw" / "archive.zip"
            invalid_xlsx.parent.mkdir(parents=True, exist_ok=True)
            invalid_xlsx.write_text("xlsx placeholder", encoding="utf-8")
            invalid_zip.write_text("zip placeholder", encoding="utf-8")

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(invalid_xlsx), str(db_path), str(invalid_zip)],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(db_path.resolve()))
            self.assertFalse(report["degraded"])
            self.assertEqual(
                report["ignored_invalid_sqlite_paths"],
                [_workspace_rel(workspace, invalid_xlsx), _workspace_rel(workspace, invalid_zip)],
            )

    def test_run_audit_degrades_when_no_usable_sqlite_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [],
                    "scan_dirs": [],
                },
            )

            self.assertIsNone(report["database"])
            self.assertTrue(report["degraded"])
            self.assertEqual(report["status"], "degraded")
            self.assertEqual(report["outcome_status"], "degraded")
            self.assertIn("可用 SQLite", report["business_status_zh"])
            self.assertIn("sqlite_paths", report["recommended_next_action"])
            self.assertEqual(report["issues"][0]["type"], "missing_usable_sqlite")
            self.assertEqual(report["artifact_guidance"][0]["artifact"], "data_quality_audit.latest.json")
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit.latest.json").is_file())
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit_report.md").is_file())

    def test_run_audit_degrades_when_sqlite_paths_only_contain_non_sqlite_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            xlsx_path = workspace / "cases" / "demo_case" / "raw" / "stations.xlsx"
            zip_path = workspace / "cases" / "demo_case" / "raw" / "package.zip"
            xlsx_path.parent.mkdir(parents=True, exist_ok=True)
            xlsx_path.write_text("xlsx placeholder", encoding="utf-8")
            zip_path.write_text("zip placeholder", encoding="utf-8")

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(xlsx_path), str(zip_path)],
                    "scan_dirs": [],
                },
            )

            self.assertTrue(report["degraded"])
            self.assertEqual(
                report["ignored_invalid_sqlite_paths"],
                [_workspace_rel(workspace, xlsx_path), _workspace_rel(workspace, zip_path)],
            )
            self.assertEqual(report["issues"][0]["type"], "missing_usable_sqlite")

    def test_run_audit_ignores_fake_sqlite_file_and_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            fake_db = workspace / "cases" / "demo_case" / "data" / "fake.sqlite"
            fake_db.parent.mkdir(parents=True, exist_ok=True)
            fake_db.write_text("not a sqlite database", encoding="utf-8")

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(fake_db)],
                    "scan_dirs": [],
                },
            )

            self.assertTrue(report["degraded"])
            self.assertIsNone(report["database"])
            self.assertEqual(report["status"], "degraded")
            self.assertEqual(report["issues"][0]["type"], "missing_usable_sqlite")
            self.assertEqual(report["ignored_invalid_sqlite_paths"], [_workspace_rel(workspace, fake_db)])

    def test_run_audit_uses_real_sqlite_from_scan_dirs_and_degrades_without_timeseries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            scan_dir = workspace / "scan"
            scan_dir.mkdir(parents=True, exist_ok=True)
            fake_db = scan_dir / "bad.sqlite"
            fake_db.write_text("not a sqlite database", encoding="utf-8")
            schema_poor_db = scan_dir / "schema_poor.sqlite"
            self._create_schema_poor_db(schema_poor_db)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [],
                    "scan_dirs": [str(scan_dir)],
                },
            )

            self.assertEqual(report["database"], str(schema_poor_db.resolve()))
            self.assertTrue(report["degraded"])
            self.assertEqual(report["status"], "degraded")
            self.assertEqual(report["outcome_status"], "degraded")
            self.assertIn("timeseries", report["recommended_next_action"])
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit.latest.json").is_file())
            self.assertTrue((workspace / "cases" / "demo_case" / "contracts" / "data_quality_audit_report.md").is_file())

    def test_run_audit_prefers_supported_schema_sqlite_over_legacy_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            legacy_db = workspace / "cases" / "demo_case" / "data" / "legacy.sqlite"
            preferred_db = workspace / "cases" / "demo_case" / "data" / "preferred.sqlite"
            self._create_schema_poor_db(legacy_db)
            self._create_demo_db(preferred_db)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(legacy_db), str(preferred_db)],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(preferred_db.resolve()))
            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertIn("timeseries", report["tables"])

    def test_run_audit_resolves_workspace_relative_sqlite_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "relative" / "demo.sqlite"
            self._create_demo_db(db_path)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": ["relative/demo.sqlite"],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(db_path.resolve()))
            self.assertFalse(report["degraded"])

    def test_run_audit_warns_when_observations_missing_partial_value_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "observations_only_z.sqlite"
            self._create_observations_db(db_path, include_z=True, include_q=False)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["tables"]["observations"]["row_count"], 1)
            self.assertIn("water_level", report["station_audit"]["S-001"]["variables"])
            self.assertNotIn("flow", report["station_audit"]["S-001"]["variables"])
            self.assertTrue(any(issue["type"] == "partial_observations_schema" for issue in report["issues"]))

    def test_run_audit_detects_minute_gaps_and_negative_flow_in_observations_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "observations_behavior.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
                conn.executemany(
                    "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
                    [
                        ("S-001", "2026-01-01 00:00:00", 123.4, 56.7),
                        ("S-001", "2026-01-01 00:01:00", 123.5, 56.8),
                        ("S-001", "2026-01-01 00:03:00", 123.7, -1.0),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["station_audit"]["S-001"]["variables"]["water_level"]["total_gaps"], 1)
            self.assertEqual(report["station_audit"]["S-001"]["variables"]["flow"]["negative_count"], 1)
            self.assertTrue(
                any(
                    issue["type"] == "time_gaps"
                    and issue.get("station") == "S-001"
                    and issue.get("variable") == "water_level"
                    for issue in report["issues"]
                )
            )
            self.assertTrue(
                any(
                    issue["type"] == "negative_values"
                    and issue.get("station") == "S-001"
                    and issue.get("variable") == "flow"
                    for issue in report["issues"]
                )
            )
            self.assertEqual(report["scores"]["completeness"], 3)

    def test_run_audit_detects_minute_gaps_in_supported_timeseries_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "timeseries_gap.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE stations (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        station_type TEXT,
                        lat REAL,
                        lon REAL,
                        elevation REAL,
                        basin_area_km2 REAL,
                        source TEXT,
                        metadata_json TEXT
                    );
                    CREATE TABLE timeseries (
                        station_id TEXT NOT NULL,
                        variable TEXT NOT NULL,
                        time_step TEXT NOT NULL,
                        time TEXT NOT NULL,
                        value REAL,
                        quality INTEGER,
                        PRIMARY KEY (station_id, variable, time_step, time)
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO stations (id, name, source, metadata_json) VALUES (?, ?, ?, ?)",
                    ("24001201", "取水口", "station_meta.csv", json.dumps({}, ensure_ascii=False)),
                )
                conn.executemany(
                    "INSERT INTO timeseries (station_id, variable, time_step, time, value, quality) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        ("24001201", "water_level", "1min", "2026-01-01 00:00:00", 347.34, 1),
                        ("24001201", "water_level", "1min", "2026-01-01 00:01:00", 347.35, 1),
                        ("24001201", "water_level", "1min", "2026-01-01 00:03:00", 347.37, 1),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["station_audit"]["24001201"]["variables"]["water_level"]["total_gaps"], 1)
            self.assertEqual(report["station_audit"]["24001201"]["variables"]["water_level"]["gaps"][0]["from"], "2026-01-01 00:01:00")
            self.assertEqual(report["station_audit"]["24001201"]["variables"]["water_level"]["gaps"][0]["to"], "2026-01-01 00:03:00")
            self.assertAlmostEqual(report["station_audit"]["24001201"]["variables"]["water_level"]["gaps"][0]["hours"], 2 / 60)
            self.assertTrue(
                any(
                    issue["type"] == "time_gaps"
                    and issue.get("station") == "24001201"
                    and issue.get("variable") == "water_level"
                    for issue in report["issues"]
                )
            )
            self.assertEqual(report["scores"]["completeness"], 3)

    def test_run_audit_separates_gap_detection_by_time_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "timeseries_mixed_step.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE stations (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        station_type TEXT,
                        lat REAL,
                        lon REAL,
                        elevation REAL,
                        basin_area_km2 REAL,
                        source TEXT,
                        metadata_json TEXT
                    );
                    CREATE TABLE timeseries (
                        station_id TEXT NOT NULL,
                        variable TEXT NOT NULL,
                        time_step TEXT NOT NULL,
                        time TEXT NOT NULL,
                        value REAL,
                        quality INTEGER,
                        PRIMARY KEY (station_id, variable, time_step, time)
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO stations (id, name, source, metadata_json) VALUES (?, ?, ?, ?)",
                    ("24001201", "取水口", "station_meta.csv", json.dumps({}, ensure_ascii=False)),
                )
                conn.executemany(
                    "INSERT INTO timeseries (station_id, variable, time_step, time, value, quality) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        ("24001201", "water_level", "1min", "2026-01-01 00:00:00", 347.34, 1),
                        ("24001201", "water_level", "1min", "2026-01-01 00:01:00", 347.35, 1),
                        ("24001201", "water_level", "1min", "2026-01-01 00:03:00", 347.37, 1),
                        ("24001201", "water_level", "1h", "2026-01-01 00:00:00", 347.00, 1),
                        ("24001201", "water_level", "1h", "2026-01-01 01:00:00", 347.10, 1),
                        ("24001201", "water_level", "1h", "2026-01-01 02:00:00", 347.20, 1),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["station_audit"]["24001201"]["variables"]["water_level"]["total_gaps"], 1)
            self.assertAlmostEqual(
                report["station_audit"]["24001201"]["variables"]["water_level"]["gaps"][0]["hours"],
                2 / 60,
            )
            self.assertEqual(
                sum(
                    1
                    for issue in report["issues"]
                    if issue["type"] == "time_gaps"
                    and issue.get("station") == "24001201"
                    and issue.get("variable") == "water_level"
                ),
                1,
            )

    def test_run_audit_degrades_when_observations_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "invalid_observations.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE observations (time TEXT, Z REAL)")
                conn.execute("INSERT INTO observations (time, Z) VALUES (?, ?)", ("2026-01-01T00:00:00", 123.4))
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertTrue(report["degraded"])
            self.assertEqual(report["issues"][0]["type"], "unsupported_observations_schema")
            self.assertIn("station", report["issues"][0]["message"])

    def test_run_audit_prefers_truly_supported_schema_over_invalid_observations_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            invalid_db = workspace / "cases" / "demo_case" / "data" / "invalid_observations.sqlite"
            preferred_db = workspace / "cases" / "demo_case" / "data" / "preferred.sqlite"
            invalid_db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(invalid_db)
            try:
                conn.execute("CREATE TABLE observations (time TEXT, Z REAL)")
                conn.execute("INSERT INTO observations (time, Z) VALUES (?, ?)", ("2026-01-01T00:00:00", 123.4))
                conn.commit()
            finally:
                conn.close()
            self._create_demo_db(preferred_db)

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(invalid_db), str(preferred_db)],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(preferred_db.resolve()))
            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")

    def test_run_audit_falls_back_to_valid_observations_when_timeseries_table_is_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "mixed.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE timeseries (station_id TEXT, variable TEXT)")
                conn.execute("CREATE TABLE observations (station TEXT, time TEXT, Z REAL, Q REAL)")
                conn.executemany(
                    "INSERT INTO observations (station, time, Z, Q) VALUES (?, ?, ?, ?)",
                    [
                        ("S-001", "2026-01-01 00:00:00", 123.4, 56.7),
                        ("S-001", "2026-01-01 00:01:00", 123.5, 56.8),
                        ("S-001", "2026-01-01 00:03:00", 123.7, 57.0),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertEqual(report["database"], str(db_path.resolve()))
            self.assertFalse(report["degraded"])
            self.assertEqual(report["status"], "completed")
            self.assertIn("water_level", report["station_audit"]["S-001"]["variables"])
            self.assertEqual(report["station_audit"]["S-001"]["variables"]["water_level"]["total_gaps"], 1)
            self.assertTrue(any(issue["type"] == "unsupported_timeseries_schema" for issue in report["issues"]))
            self.assertTrue(any(issue["type"] == "time_gaps" for issue in report["issues"]))

    def test_run_audit_preserves_timeseries_schema_issue_when_observations_are_also_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            db_path = workspace / "cases" / "demo_case" / "data" / "mixed_invalid.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE timeseries (station_id TEXT, variable TEXT)")
                conn.execute("CREATE TABLE observations (time TEXT, Z REAL)")
                conn.execute(
                    "INSERT INTO observations (time, Z) VALUES (?, ?)",
                    ("2026-01-01T00:00:00", 123.4),
                )
                conn.commit()
            finally:
                conn.close()

            report = self._run_audit(
                workspace,
                {
                    "sqlite_paths": [str(db_path)],
                    "scan_dirs": [],
                },
            )

            self.assertTrue(report["degraded"])
            self.assertEqual(report["status"], "degraded")
            self.assertTrue(any(issue["type"] == "unsupported_timeseries_schema" for issue in report["issues"]))
            self.assertTrue(any(issue["type"] == "unsupported_observations_schema" for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
