import json
import os
import argparse
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = ROOT_DIR / "cases"
REGISTRIES_DIR = ROOT_DIR / "Hydrology" / "configs" / "core_registries"

def load_template_registry():
    with open(REGISTRIES_DIR / "report_templates.generated.json", "r") as f:
        return json.load(f)["templates"]

def generate_report(case_id, template_key, context):
    templates = load_template_registry()
    template = next((t for t in templates if t["key"] == template_key), None)
    if not template:
        print(f"Template {template_key} not found.")
        return

    today = datetime.now().strftime("%Y%m%d")
    output_path_str = template["output_path_convention"].format(case_id=case_id, date=today, release_id=context.get("release_id", "v1.0"))
    
    out_file = ROOT_DIR / output_path_str
    out_file.parent.mkdir(parents=True, exist_ok=True)

    report_content = f"# {template['name']} for {case_id}\n\n"
    report_content += f"**Date:** {today}\n"
    for field in template["required_fields"]:
        val = context.get(field, "N/A")
        report_content += f"**{field.capitalize()}:** {val}\n\n"

    with open(out_file, "w") as f:
        f.write(report_content)
    print(f"Generated report at {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, help="Case ID")
    parser.add_argument("--template", required=True, help="Template Key")
    parser.add_argument("--context", type=json.loads, default="{}", help="JSON context")
    args = parser.parse_args()

    generate_report(args.case, args.template, args.context)
