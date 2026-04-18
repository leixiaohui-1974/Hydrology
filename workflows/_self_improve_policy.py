"""向后兼容：请改用 workflows._autonomy_policy。"""
from __future__ import annotations

from typing import Any

from workflows._autonomy_policy import (  # noqa: F401
    argv_has,
    governance_source_relpath,
    load_merged_autonomy_policy,
    load_raw_autonomy_yaml,
    policy_section,
    section,
)


def merged_sections(case_id: str, config_path: str | None = None) -> dict[str, dict[str, Any]]:
    p = load_merged_autonomy_policy(case_id, config_path)
    return {k: dict(v) for k, v in p.items() if isinstance(v, dict)}
