"""Workflow-template mapping integrity tests."""

from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from workflows import WORKFLOW_REGISTRY
from workflows import outcome_contract
from generate_core_registries import generate_workflow_registry


class TestWorkflowTemplateMapping(unittest.TestCase):
    def test_mapping_references_existing_templates(self) -> None:
        templates_path = ROOT_DIR / "configs" / "outcome_templates.yaml"
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        templates = yaml.safe_load(templates_path.read_text(encoding="utf-8")) or {}
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}

        template_ids = set((templates.get("templates") or {}).keys())
        self.assertIn("generic_template", template_ids)

        default_template = mapping.get("default_template")
        self.assertIn(default_template, template_ids)

        for wf_key, wf_cfg in (mapping.get("workflows") or {}).items():
            self.assertIn(wf_key, WORKFLOW_REGISTRY)
            wf_cfg = wf_cfg or {}
            if wf_cfg.get("report_exempt"):
                continue
            template_id = wf_cfg.get("template_id")
            self.assertIn(template_id, template_ids)

    def test_workflow_registry_keys_covered_by_mapping(self) -> None:
        templates_path = ROOT_DIR / "configs" / "outcome_templates.yaml"
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        templates = yaml.safe_load(templates_path.read_text(encoding="utf-8")) or {}
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        template_ids = set((templates.get("templates") or {}).keys())
        workflows = mapping.get("workflows") or {}

        for wf_key in sorted(WORKFLOW_REGISTRY.keys()):
            self.assertIn(wf_key, workflows, f"workflow_template_mapping missing key: {wf_key}")
            wf_cfg = workflows[wf_key] or {}
            if wf_cfg.get("report_exempt"):
                tid = wf_cfg.get("template_id")
                if tid is not None:
                    self.assertIn(tid, template_ids, wf_key)
                continue
            template_id = wf_cfg.get("template_id")
            self.assertIsNotNone(template_id, wf_key)
            self.assertIn(template_id, template_ids, wf_key)

    def test_algorithm_metric_packs_exist(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        packs = mapping.get("algorithm_metric_packs") or {}
        self.assertIn("default", packs)
        self.assertGreater(len(packs.get("default", [])), 0)

    def test_select_template_accepts_canonical_workflow_key(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}

        template_id, category, algorithm_tags = outcome_contract._select_template(
            "state_estimation",
            mapping,
        )

        self.assertEqual(template_id, "calibration_assimilation_template")
        self.assertEqual(category, "calibration_assimilation")
        self.assertEqual(algorithm_tags, ["default"])

    def test_high_value_external_alias_workflows_not_generic(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        workflows = mapping.get("workflows") or {}
        high_value = [
            "legacy_hydro_coupling_ext",
            "strict_revalidation_ext",
            "hil_acceptance_test_ext",
            "wnal_evaluation_ext",
            "pipedream_report_ext",
        ]
        for wf_key in high_value:
            self.assertIn(wf_key, workflows)
            template_id = (workflows[wf_key] or {}).get("template_id")
            self.assertIsNotNone(template_id)
            self.assertNotEqual(template_id, "generic_template")

    def test_object_oriented_workflows_use_object_templates(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        workflows = mapping.get("workflows") or {}

        expected = {
            "source_to_delineation": ("watershed_object_template", "object_watershed"),
            "hydro_report": ("watershed_object_template", "object_watershed"),
            "section_analysis": ("channel_object_template", "object_channel"),
            "hyd_sim": ("reservoir_object_template", "object_reservoir"),
            "hyd_report": ("reservoir_object_template", "object_reservoir"),
            "cascade": ("reservoir_object_template", "object_reservoir"),
        }

        for wf_key, (template_id, category) in expected.items():
            wf_cfg = workflows.get(wf_key)
            self.assertIsNotNone(wf_cfg, wf_key)
            self.assertEqual(wf_cfg.get("template_id"), template_id, wf_key)
            self.assertEqual(wf_cfg.get("category"), category, wf_key)

    def test_daduhe_bound_external_aliases_removed(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        workflows = mapping.get("workflows") or {}
        retired_aliases = {
            "daduhe_full_pipeline_ext",
            "daduhe_pipedream_ext",
            "daduhe_hydro_coupling_ext",
            "daduhe_historical_validation_ext",
            "daduhe_real_validation_ext",
            "daduhe_ekf_mpc_ext",
        }

        for wf_key in retired_aliases:
            self.assertNotIn(wf_key, WORKFLOW_REGISTRY)
            self.assertNotIn(wf_key, workflows)

    def test_legacy_script_aliases_removed_from_product_registry(self) -> None:
        mapping_path = ROOT_DIR / "configs" / "workflow_template_mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
        workflows = mapping.get("workflows") or {}
        retired_aliases = {
            "legacy_full_pipeline_ext",
            "legacy_pipedream_ext",
            "legacy_historical_validation_ext",
            "legacy_real_validation_ext",
            "legacy_ekf_mpc_ext",
        }

        for wf_key in retired_aliases:
            self.assertNotIn(wf_key, WORKFLOW_REGISTRY)
            self.assertNotIn(wf_key, workflows)

    def test_object_templates_define_six_standard_object_types(self) -> None:
        templates_path = ROOT_DIR / "configs" / "outcome_templates.yaml"
        registry_path = ROOT_DIR / "configs" / "core_registries" / "report_templates.generated.json"
        templates = yaml.safe_load(templates_path.read_text(encoding="utf-8")) or {}
        registry = json.loads(registry_path.read_text(encoding="utf-8"))

        expected = {
            "reservoir_object_template": "Reservoir",
            "channel_object_template": "Channel",
            "pump_station_object_template": "PumpStation",
            "gate_object_template": "Gate",
            "pipeline_object_template": "Pipeline",
            "watershed_object_template": "Watershed",
        }

        for template_id, object_type in expected.items():
            template_cfg = (templates.get("templates") or {}).get(template_id)
            self.assertIsNotNone(template_cfg, template_id)
            self.assertEqual(template_cfg.get("object_type"), object_type)
            self.assertEqual(template_cfg.get("selection_mode"), "object_type")
            self.assertTrue(template_cfg.get("schema_definition"))
            self.assertGreaterEqual(len(template_cfg.get("markdown_sections") or []), 4)
            self.assertGreaterEqual(len(template_cfg.get("json_required_fields") or []), 5)

        registry_items = {
            item["key"]: item
            for item in registry.get("templates", [])
        }
        for template_id, object_type in expected.items():
            entry = registry_items.get(template_id)
            self.assertIsNotNone(entry, template_id)
            self.assertEqual(entry.get("object_type"), object_type)
            self.assertEqual(entry.get("selection_mode"), "object_type")
            self.assertTrue(entry.get("schema_definition"))
            self.assertGreaterEqual(len(entry.get("markdown_sections") or []), 4)

    def test_generated_workflow_registry_projects_canonical_metadata(self) -> None:
        generate_workflow_registry()
        registry_path = ROOT_DIR / "configs" / "core_registries" / "workflow_registry.generated.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        items = {item["key"]: item for item in registry.get("workflows", [])}

        self.assertEqual(items["state_est"]["canonical_key"], "state_estimation")
        self.assertEqual(items["state_est"]["legacy_aliases"], ["state_est"])
        self.assertEqual(items["state_est"]["workflow_level"], "execution")
        self.assertEqual(items["state_est"]["business_domain"], "optimization_control")
        self.assertEqual(items["source_to_delineation"]["phase"], "object_watershed")
        self.assertEqual(items["source_to_delineation"]["template_id"], "watershed_object_template")
        self.assertEqual(items["section_analysis"]["phase"], "object_channel")
        self.assertEqual(items["hyd_report"]["phase"], "object_reservoir")


if __name__ == "__main__":
    unittest.main()
