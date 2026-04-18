import os
import json
import yaml
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = ROOT_DIR / "cases"
CONFIGS_DIR = ROOT_DIR / "Hydrology" / "configs"
OUT_DIR = CONFIGS_DIR / "core_registries"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_CANONICALIZATION_PATH = ROOT_DIR.parent / "hydromind" / "configs" / "platform" / "workflow_canonicalization.v1.yaml"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _workflow_canonical_meta(workflow_key: str, payload: dict) -> dict:
    workflows = dict(payload.get("workflows") or {})
    normalized = str(workflow_key or "").strip()
    if not normalized:
        return {"canonical_key": "", "legacy_aliases": []}
    for canonical_key, meta in workflows.items():
        aliases = [str(item).strip() for item in list((meta or {}).get("legacy_aliases") or []) if str(item).strip()]
        if normalized == str(canonical_key).strip() or normalized in aliases:
            return {
                "canonical_key": str(canonical_key).strip(),
                "legacy_aliases": aliases,
                "workflow_level": str((meta or {}).get("workflow_level") or "").strip(),
                "business_domain": str((meta or {}).get("business_domain") or "").strip(),
                "default_visibility": str((meta or {}).get("default_visibility") or "").strip(),
            }
    return {
        "canonical_key": normalized,
        "legacy_aliases": [],
        "workflow_level": "",
        "business_domain": "",
        "default_visibility": "",
    }

def generate_cases_catalog():
    catalog = {"version": "1.0", "cases": []}
    if CASES_DIR.exists():
        for case_dir in CASES_DIR.iterdir():
            if case_dir.is_dir() and (case_dir / "manifest.yaml").exists():
                with open(case_dir / "manifest.yaml", "r") as f:
                    manifest = yaml.safe_load(f) or {}
                catalog["cases"].append({
                    "id": case_dir.name,
                    "name": manifest.get("name", case_dir.name),
                    "description": manifest.get("description", ""),
                    "type": manifest.get("type", "Simulation"),
                    "status": "ready"
                })
    with open(OUT_DIR / "cases_catalog.generated.json", "w") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

def generate_workflow_registry():
    registry = {"version": "1.0", "workflows": []}
    wf_map_path = CONFIGS_DIR / "workflow_template_mapping.yaml"
    canonicalization = _load_yaml(WORKFLOW_CANONICALIZATION_PATH)
    if wf_map_path.exists():
        wf_data = _load_yaml(wf_map_path)
            
        for k, v in wf_data.get("workflows", {}).items():
            canonical_meta = _workflow_canonical_meta(k, canonicalization)
            registry["workflows"].append({
                "key": k,
                "canonical_key": canonical_meta.get("canonical_key") or k,
                "legacy_aliases": canonical_meta.get("legacy_aliases") or [],
                "name": k.replace("_", " ").title(),
                "phase": v.get("category", "unknown"),
                "template_id": v.get("template_id", ""),
                "algorithm_tags": v.get("algorithm_tags", []),
                "workflow_level": canonical_meta.get("workflow_level") or None,
                "business_domain": canonical_meta.get("business_domain") or None,
                "default_visibility": canonical_meta.get("default_visibility") or None,
            })
            
    with open(OUT_DIR / "workflow_registry.generated.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

def generate_model_algo_registry():
    registry = {"version": "1.0", "algorithms": []}
    agent_reg_path = CONFIGS_DIR / "agent_registry.yaml"
    
    if agent_reg_path.exists():
        with open(agent_reg_path, "r") as f:
            agents_data = yaml.safe_load(f) or {}
            
        for agent_key, agent_info in agents_data.get("agents", {}).items():
            for mod in agent_info.get("modules", []):
                # Map algorithms to simulation, assimilation, calibration, and scheduling
                algo_type = "simulation" # default
                mod_lower = mod.lower()
                agent_phase = agent_info.get("lifecycle_phase", "").lower()
                
                if "assimilation" in mod_lower or "enkf" in mod_lower or "state_estimation" in mod_lower:
                    algo_type = "assimilation"
                elif "calibration" in mod_lower or "identifi" in mod_lower or "transfer" in mod_lower or "autolearn" in mod_lower or "率定" in agent_phase or "辨识" in agent_phase:
                    algo_type = "calibration"
                elif "schedul" in mod_lower or "dispatch" in mod_lower or "control" in mod_lower or "mpc" in mod_lower or "调度" in agent_phase or "控制" in agent_phase:
                    algo_type = "scheduling"
                elif "simulat" in mod_lower or "model" in mod_lower or "cascade" in mod_lower or "routing" in mod_lower or "runoff" in mod_lower or "仿真" in agent_phase or "推演" in agent_phase:
                    algo_type = "simulation"
                
                registry["algorithms"].append({
                    "key": mod.split(".")[-1],
                    "name": mod,
                    "type": algo_type,
                    "agent": agent_key
                })
                
    with open(OUT_DIR / "model_algo_registry.generated.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

def generate_report_template_registry():
    registry = {"version": "1.0", "templates": []}
    outcome_path = CONFIGS_DIR / "outcome_templates.yaml"
    wf_map_path = CONFIGS_DIR / "workflow_template_mapping.yaml"
    
    slot_mapping = {}
    if wf_map_path.exists():
        with open(wf_map_path, "r") as f:
            wf_data = yaml.safe_load(f) or {}
            slot_mapping = wf_data.get("artifact_slot_mapping", {})
            
    if outcome_path.exists():
        with open(outcome_path, "r") as f:
            outcome_data = yaml.safe_load(f) or {}
            
        for tpl_key, tpl_info in outcome_data.get("templates", {}).items():
            dims = tpl_info.get("required_dimensions", [])
            # Map report templates to outcome artifacts
            artifacts = []
            for dim in dims:
                found = False
                for slot, mapped_dims in slot_mapping.items():
                    if dim in mapped_dims:
                        artifacts.append(slot)
                        found = True
                if not found:
                    artifacts.append(dim)
                    
            template_entry = {
                "key": tpl_key,
                "name": tpl_info.get("name", tpl_key),
                "phase": tpl_info.get("category", "general"),
                "outcome_artifacts": sorted(list(set(artifacts))),
                "required_dimensions": list(dims),
                "required_fields": list(tpl_info.get("required_fields") or []),
                "output_path_convention": tpl_info.get("output_path_convention") or f"reports/{tpl_key}/{{case_id}}.{{date}}.md",
            }
            for field in (
                "object_type",
                "selection_mode",
                "schema_definition",
                "deprecated_alias_for",
                "markdown_sections",
                "json_required_fields",
            ):
                value = tpl_info.get(field)
                if value:
                    template_entry[field] = value

            registry["templates"].append(template_entry)
            
    with open(OUT_DIR / "report_templates.generated.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    generate_cases_catalog()
    generate_workflow_registry()
    generate_model_algo_registry()
    generate_report_template_registry()
    print("Successfully generated 4 core registries in", OUT_DIR)
