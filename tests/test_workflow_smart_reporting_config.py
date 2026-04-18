"""workflow_smart_reporting 产品化配置加载与路径模板。"""
from __future__ import annotations

from workflows.smart_run_reporting import (
    _artifact_path_ctx,
    _build_bundle_rel_paths,
    load_workflow_smart_reporting_config,
)


def test_load_default_has_md_regeneration_keys():
    cfg = load_workflow_smart_reporting_config("daduhe")
    md = cfg.get("md_regeneration") or {}
    keys = md.get("workflow_keys") or []
    assert isinstance(keys, list)
    assert "hydro_report" in keys
    assert cfg.get("_config_source")


def test_bundle_path_templates_use_contract_filenames():
    cfg = load_workflow_smart_reporting_config("daduhe")
    cfg.setdefault("contract_filenames", {})
    if isinstance(cfg["contract_filenames"], dict):
        cfg["contract_filenames"]["run_summary"] = "custom_summary.json"
    ctx = _artifact_path_ctx("xcase", cfg)
    assert ctx["run_summary_file"] == "custom_summary.json"
    paths = _build_bundle_rel_paths("simple", "xcase", cfg, skip_universal=False)
    assert any("custom_summary.json" in p for p in paths.values())


def test_per_case_merge_monkeypatch(tmp_path, monkeypatch):
    """per_case 覆盖 md_regeneration（不写真实 daduhe.yaml）。"""
    yml = tmp_path / "rep.yaml"
    yml.write_text(
        """
defaults:
  md_regeneration:
    workflow_keys: [a]
per_case:
  merge_test_case:
    md_regeneration:
      workflow_keys: [hydro_report]
""",
        encoding="utf-8",
    )

    import workflows.smart_run_reporting as sr

    monkeypatch.setattr(sr, "DEFAULT_SMART_REPORTING_YAML", yml)
    monkeypatch.setattr(
        "workflows._shared.load_case_config",
        lambda _cid, _p=None: {"case_id": _cid},
    )

    cfg = load_workflow_smart_reporting_config("merge_test_case", reporting_yaml=str(yml))
    keys = (cfg.get("md_regeneration") or {}).get("workflow_keys") or []
    assert keys == ["hydro_report"]
