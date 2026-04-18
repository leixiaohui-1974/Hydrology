"""business_run_digest：业务汇编渲染回归。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydro_model import business_run_digest as digest_module
from hydro_model import object_report_generator as object_report_module
from hydro_model.business_run_digest import (
    _render_markdown_include,
    _render_topology_standard_object_matrix,
    build_business_digest_markdown,
    write_business_run_digest,
)
from hydro_model.object_report_generator import ObjectReportGenerator


@pytest.fixture()
def fake_contracts(tmp_path: Path) -> Path:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    index = {
        "case_id": "ut",
        "reports": [
            {
                "object_type": "Reservoir",
                "status": "available",
                "object_id": "r1",
                "display_name": "测试库",
                "json_path": "object_reports/x.json",
                "markdown_path": "object_reports/x.md",
            },
            {
                "object_type": "Gate",
                "status": "missing",
                "default_strategy": "missing_in_case_skip_sample",
                "reason": "topology 无 Gate",
            },
        ],
    }
    (contracts / "standard_object_reports.index.json").write_text(
        json.dumps(index, ensure_ascii=False),
        encoding="utf-8",
    )
    return contracts


def test_topology_matrix_includes_contract_types(fake_contracts: Path) -> None:
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {"index_path": "standard_object_reports.index.json", "list_source_artifacts": False}
    digest = {"object_type_labels_zh": {"Reservoir": "水库测试标签"}}
    md = _render_topology_standard_object_matrix(fake_contracts, ctx, block, digest=digest)
    assert "Reservoir" in md
    assert "水库测试标签" in md
    assert "Gate" in md
    assert "topology 无 Gate" in md
    assert "PumpStation" in md


def test_object_report_generator_persists_workspace_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path
    report_dir = workspace / "cases" / "demo" / "contracts" / "object_reports"
    monkeypatch.setattr(object_report_module, "WORKSPACE", workspace)
    generator = ObjectReportGenerator("demo", report_dir)

    payload = generator.generate_report(
        object_type="Reservoir",
        object_id="r1",
        display_name="测试库",
        metrics={"RMSE": 0.1},
        details={},
    )
    index_path = generator.save_index()
    index = json.loads(index_path.read_text(encoding="utf-8"))

    assert payload is not None
    assert index["reports"][0]["json_path"] == "cases/demo/contracts/object_reports/reservoir_r1.report.json"
    assert index["reports"][0]["markdown_path"] == "cases/demo/contracts/object_reports/reservoir_r1.report.md"


def test_markdown_include_can_strip_title_metadata_and_headings(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = contracts / "sample.md"
    source.write_text(
        "# 技术标题\n\n## 保留章节\n\n保留内容。\n\n## 来源 ##\n\n来源内容。\n\n*数据来源: demo*\n*工作流: demo*\n*_auto_generated: true*\n",
        encoding="utf-8",
    )
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {
        "path": "sample.md",
        "strip_title": True,
        "strip_trailing_metadata": True,
        "exclude_headings": ["来源"],
    }

    md = _render_markdown_include(contracts, ctx, block)

    assert "技术标题" not in md
    assert "保留内容。" in md
    assert "来源内容。" not in md
    assert "数据来源" not in md
    assert "工作流" not in md
    assert "auto_generated" not in md


def test_business_digest_header_hides_technical_module_name(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "overview",
                    "title_zh": "概览",
                    "blocks": [{"type": "static_note", "body_zh": "这里是业务摘要。"}],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "hydro_model.business_run_digest" not in md
    assert "pipedream-hydrology-integration-lab" not in md
    assert "- **用途**:" in md
    assert "这里是业务摘要。" in md


def test_markdown_include_truncation_keeps_code_fence_closed(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = contracts / "sample.md"
    source.write_text(
        "# 标题\n\n```json\n{\n  \"a\": 1,\n  \"b\": 2\n}\n```\n\n尾部说明\n",
        encoding="utf-8",
    )
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {"path": "sample.md", "strip_title": True, "max_chars": 20}

    md = _render_markdown_include(contracts, ctx, block)

    assert md.count("```") % 2 == 0
    assert "已按配置截断" in md
    assert "完整路径" in md


def test_markdown_include_can_strip_leading_blockquote_metadata(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = contracts / "sample.md"
    source.write_text(
        "> 自动生成 | case_id: ut\n> _系统说明_\n\n## 摘要\n\n业务内容。\n",
        encoding="utf-8",
    )
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {"path": "sample.md", "strip_leading_blockquote_metadata": True}

    md = _render_markdown_include(contracts, ctx, block)

    assert "自动生成" not in md
    assert "系统说明" not in md
    assert "业务内容。" in md


def test_markdown_include_preserves_non_metadata_leading_blockquote(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = contracts / "sample.md"
    source.write_text(
        "> 重要结论：本轮来水偏枯，建议按保供优先调度。\n\n## 摘要\n\n业务内容。\n",
        encoding="utf-8",
    )
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {"path": "sample.md", "strip_leading_blockquote_metadata": True}

    md = _render_markdown_include(contracts, ctx, block)

    assert "重要结论：本轮来水偏枯" in md
    assert "业务内容。" in md


def test_markdown_include_preserves_business_blockquote_with_metadata_keywords(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = contracts / "sample.md"
    source.write_text(
        "> 工作流建议：先完成数据复核，再进入会商。\n> 生成时间窗口内来水偏枯，应关注保供安全。\n\n## 摘要\n\n业务内容。\n",
        encoding="utf-8",
    )
    ctx = {"case_id": "ut", "plan_file": "p.json", "run_summary_file": "s.json", "universal_html_file": "u.html"}
    block = {"path": "sample.md", "strip_leading_blockquote_metadata": True}

    md = _render_markdown_include(contracts, ctx, block)

    assert "工作流建议：先完成数据复核" in md
    assert "生成时间窗口内来水偏枯" in md
    assert "业务内容。" in md


def test_write_business_run_digest_fails_fast_when_sections_missing(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})

    reporting_cfg = {"business_run_digest": {"title_zh": "业务版汇总", "sections": []}}

    with pytest.raises(ValueError, match="sections"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_fast_when_all_blocks_are_placeholders(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "placeholder-only",
                    "title_zh": "占位章节",
                    "blocks": [{"type": "markdown_include", "path": "missing.md"}],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_fast_when_only_intro_and_static_notes_exist(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "placeholder-only",
                    "title_zh": "占位章节",
                    "intro_zh": "这是章节说明。",
                    "blocks": [
                        {"type": "static_note", "body_zh": "这是说明性提示。"},
                        {"type": "markdown_include", "path": "missing.md"},
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_build_business_digest_accepts_nested_json_bullets_as_effective_data(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "final_report.latest.json").write_text(
        json.dumps(
            {
                "schema_version": "final_report.v1",
                "readiness": {"platform": {"ok": True}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "final-gate-only",
                    "title_zh": "交付状态",
                    "blocks": [
                        {
                            "type": "nested_json_bullets",
                            "path": "final_report.latest.json",
                            "picks": [
                                {"label": "汇编版本", "json_path": "schema_version"},
                                {"label": "平台就绪状态", "json_path": "readiness.platform.ok"},
                            ],
                        }
                    ],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "- **汇编版本**: `final_report.v1`" in md
    assert "- **平台就绪状态**: `True`" in md


def test_build_business_digest_can_render_business_friendly_nested_json_values(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "final_report.latest.json").write_text(
        json.dumps(
            {
                "schema_version": "final_report.v1",
                "readiness": {
                    "platform": {
                        "ok": True,
                        "summary": {
                            "artifact_ratio": 1.0,
                            "case_config_signal": True,
                        },
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "final-gate-only",
                    "title_zh": "交付状态",
                    "blocks": [
                        {
                            "type": "nested_json_bullets",
                            "path": "final_report.latest.json",
                            "picks": [
                                {
                                    "label": "汇编版本",
                                    "json_path": "schema_version",
                                    "value_map": {"final_report.v1": "业务交付汇编 v1"},
                                },
                                {
                                    "label": "平台就绪状态",
                                    "json_path": "readiness.platform.ok",
                                    "bool_map": {"true": "已就绪", "false": "未就绪"},
                                },
                                {
                                    "label": "交付材料完备度",
                                    "json_path": "readiness.platform.summary.artifact_ratio",
                                    "format": "percent_0",
                                },
                                {
                                    "label": "案例配置已识别",
                                    "json_path": "readiness.platform.summary.case_config_signal",
                                    "bool_map": {"true": "已识别", "false": "未识别"},
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "- **汇编版本**: 业务交付汇编 v1" in md
    assert "- **平台就绪状态**: 已就绪" in md
    assert "- **交付材料完备度**: 100%" in md
    assert "- **案例配置已识别**: 已识别" in md



def test_write_business_run_digest_still_fails_when_nested_json_bullets_only_render_placeholders(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "final_report.latest.json").write_text(
        json.dumps({"schema_version": "final_report.v1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "final-gate-only",
                    "title_zh": "交付状态",
                    "blocks": [
                        {
                            "type": "nested_json_bullets",
                            "path": "final_report.latest.json",
                            "picks": [
                                {"label": "平台就绪状态", "json_path": "readiness.platform.ok"},
                            ],
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_when_workflow_steps_table_has_no_steps(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_when_workflow_steps_table_has_only_invalid_rows(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": [None, "bad-row"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_build_business_digest_preserves_business_text_with_inline_parenthetical_emphasis(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "overview",
                    "title_zh": "概览",
                    "blocks": [
                        {"type": "static_note", "body_zh": "建议关注 _（保供优先）_ 与下游需水。"},
                    ],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "建议关注 _（保供优先）_ 与下游需水。" in md



def test_write_business_run_digest_fails_when_workflow_steps_table_has_empty_dict_rows(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": [{}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_when_workflow_steps_table_has_error_only_dict_rows(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": [{"error": "boom"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_when_workflow_steps_table_has_blank_workflow_key(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": [{"workflow_key": "   "}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_write_business_run_digest_fails_when_workflow_steps_table_has_missing_ok(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps({"steps": [{"workflow_key": "hyd_cal"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    with pytest.raises(ValueError, match="生成结果为空"):
        write_business_run_digest("ut", reporting_cfg)



def test_build_business_digest_renders_business_friendly_object_report_labels(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {})
    object_reports_dir = fake_contracts / "object_reports"
    object_reports_dir.mkdir(exist_ok=True)
    (object_reports_dir / "x.json").write_text(
        json.dumps(
            {
                "display_name": "测试库",
                "summary": "自动生成的 Reservoir 运行结果报告",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (object_reports_dir / "x.md").write_text("# 测试库\n", encoding="utf-8")

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "object_type_labels_zh": {"Reservoir": "水库（含湖池等调节水体）"},
            "object_reports": {
                "type_heading_template_zh": "对象类型：{object_type_label}",
                "item_heading_template_zh": "{display_name}",
                "default_summary_zh": "本轮运行结果报告",
                "json_label_zh": "结果文件",
                "markdown_label_zh": "阅读版说明",
                "trim_auto_summary_prefixes": ["自动生成的"],
            },
            "sections": [
                {
                    "id": "runtime-only",
                    "title_zh": "运行期对象",
                    "blocks": [
                        {
                            "type": "object_reports_index",
                            "index_path": "standard_object_reports.index.json",
                            "skip_sample_files": False,
                        }
                    ],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "### 对象类型：水库（含湖池等调节水体）" in md
    assert "#### 测试库" in md
    assert "本轮运行结果报告" in md
    assert "- 结果文件: `" in md
    assert "- 阅读版说明: `" in md
    assert "自动生成的 Reservoir 运行结果报告" not in md
    assert "- JSON:" not in md
    assert "- Markdown:" not in md


def test_write_business_run_digest_renders_only_valid_workflow_steps_when_mixed_rows_exist(
    fake_contracts: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest_module, "_contracts_dir", lambda _: fake_contracts)
    monkeypatch.setattr(digest_module, "_load_workflow_display_zh", lambda _: {"hyd_cal": "水力学率定验证"})
    (fake_contracts / "workflow_smart_run_summary.latest.json").write_text(
        json.dumps(
            {
                "steps": [
                    {"workflow_key": "hyd_cal"},
                    {"workflow_key": "hyd_cal", "ok": True, "elapsed_sec": 12.3},
                    {"workflow_key": " ", "ok": False},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    reporting_cfg = {
        "business_run_digest": {
            "title_zh": "业务版汇总",
            "sections": [
                {
                    "id": "workflow-only",
                    "title_zh": "执行情况",
                    "blocks": [
                        {
                            "type": "workflow_steps_table",
                            "source": "workflow_smart_run_summary.latest.json",
                        }
                    ],
                }
            ],
        }
    }

    md, warnings = build_business_digest_markdown("ut", reporting_cfg)

    assert warnings == []
    assert "| 1 | 水力学率定验证 | `hyd_cal` | 成功 | 12.3 | — |" in md
    assert md.count("`hyd_cal`") == 1
