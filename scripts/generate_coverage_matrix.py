#!/usr/bin/env python3
"""
生成全项目 Coverage Matrix，作为 E2E 验收唯一抓手。
根据 registries (cases, workflows) 与实际产出的 contracts 进行比对，
输出 coverage_matrix.latest.json 到每个 case，并全局汇总，
最后生成 COVERAGE_SUMMARY.md。
"""

import json
from pathlib import Path
from datetime import datetime
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_DIR = ROOT / "Hydrology" / "configs" / "core_registries"
CASES_DIR = ROOT / "cases"
REPORTS_DIR = ROOT / "reports" / "coverage"
WORKFLOW_CANONICALIZATION_PATH = ROOT.parent / "hydromind" / "configs" / "platform" / "workflow_canonicalization.v1.yaml"

def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def canonical_workflow_key(workflow_key: str, workflow_meta: dict, canonicalization: dict) -> str:
    explicit = str((workflow_meta or {}).get("canonical_key") or "").strip()
    if explicit:
        return explicit
    workflows = dict((canonicalization or {}).get("workflows") or {})
    normalized = str(workflow_key or "").strip()
    for canonical_key, meta in workflows.items():
        aliases = [str(item).strip() for item in list((meta or {}).get("legacy_aliases") or []) if str(item).strip()]
        if normalized == str(canonical_key).strip() or normalized in aliases:
            return str(canonical_key).strip()
    return normalized

def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def write_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def generate():
    cases_cat = load_json(REGISTRY_DIR / "cases_catalog.generated.json")
    wf_reg = load_json(REGISTRY_DIR / "workflow_registry.generated.json")
    canonicalization = load_yaml(WORKFLOW_CANONICALIZATION_PATH)

    cases = cases_cat.get("cases", [])
    workflows = wf_reg.get("workflows", [])

    global_matrix = []
    summary_lines = []
    
    summary_lines.append("# Coverage Matrix Summary\n")
    summary_lines.append(f"> Generated at: {datetime.now().isoformat()}\n")
    summary_lines.append("## Global Overview\n")
    
    total_expected = len(cases) * len(workflows)
    total_present = 0

    for case in cases:
        case_id = case.get("id")
        case_matrix = {
            "case_id": case_id,
            "updated_at": datetime.now().isoformat(),
            "coverage": []
        }
        
        case_present = 0
        
        for wf in workflows:
            wf_key = wf.get("key")
            canonical_key = canonical_workflow_key(str(wf_key), wf, canonicalization)
            stage = wf.get("phase", "unknown")
            template_key = wf.get("template_id", "unknown")
            algo_tags = wf.get("algorithm_tags", ["default"])
            algo_key = algo_tags[0] if algo_tags else "default"
            track = "main"

            outcome_path = CASES_DIR / case_id / "contracts" / "outcomes" / f"{wf_key}.latest.json"
            
            if outcome_path.is_file():
                status = "present"
                case_present += 1
                total_present += 1
            else:
                status = "missing"

            record = {
                "CoverageKey": {
                    "case_id": case_id,
                    "track": track,
                    "workflow_key": wf_key,
                    "canonical_workflow_key": canonical_key,
                    "algo_key": algo_key,
                    "template_key": template_key,
                    "stage": stage
                },
                "CoverageStatus": status
            }
            
            case_matrix["coverage"].append(record)
            global_matrix.append(record)

        write_json(CASES_DIR / case_id / "contracts" / "coverage_matrix.latest.json", case_matrix)
        
        # Add to summary
        coverage_pct = (case_present / len(workflows) * 100) if workflows else 0
        summary_lines.append(f"- **{case_id}**: {case_present}/{len(workflows)} ({coverage_pct:.1f}%)")

    global_data = {
        "updated_at": datetime.now().isoformat(),
        "total_expected": total_expected,
        "total_present": total_present,
        "coverage": global_matrix
    }
    write_json(REPORTS_DIR / "coverage_matrix.global.json", global_data)

    summary_lines.append("\n## Missing Details (Top Gaps)\n")
    missing_records = [r for r in global_matrix if r["CoverageStatus"] == "missing"]
    
    if not missing_records:
        summary_lines.append("🎉 All expected workflows are covered!\n")
    else:
        summary_lines.append("| Case ID | Workflow | Stage | Algorithm | Template |\n")
        summary_lines.append("|---|---|---|---|---|\n")
        # Just show up to 100 missing to avoid huge files
        for r in missing_records[:100]:
            k = r["CoverageKey"]
            summary_lines.append(f"| {k['case_id']} | {k['workflow_key']} | {k['stage']} | {k['algo_key']} | {k['template_key']} |\n")
        if len(missing_records) > 100:
            summary_lines.append(f"\n...and {len(missing_records) - 100} more missing records.\n")

    write_md(REPORTS_DIR / "COVERAGE_SUMMARY.md", "\n".join(summary_lines))
    print(f"Coverage matrix generated successfully. Total present: {total_present}/{total_expected}")

if __name__ == "__main__":
    generate()
