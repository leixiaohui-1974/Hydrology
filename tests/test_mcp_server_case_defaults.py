from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp_server import hm_health, hm_hos_compliance_report


def test_hm_health_without_explicit_case_skips_case_checks(monkeypatch):
    monkeypatch.delenv("HYDROMIND_DEFAULT_CASE_ID", raising=False)

    payload = hm_health()

    assert payload["ok"] is True
    assert payload["case_id"] is None
    assert payload["case_checks_skipped"] is True
    assert "config_exists" not in payload
    assert "case_root_exists" not in payload


def test_hm_hos_compliance_report_without_explicit_case_does_not_save(monkeypatch):
    monkeypatch.delenv("HYDROMIND_DEFAULT_CASE_ID", raising=False)

    payload = hm_hos_compliance_report(save_to_contracts=True)

    assert payload["ok"] is True
    assert payload["case_id"] is None
    assert payload["saved_path"] is None
    assert "warning" in payload
