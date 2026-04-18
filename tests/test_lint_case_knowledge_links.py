"""lint_case_knowledge_links：配置合并与 Markdown 相对链接解析。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "Hydrology" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lint_case_knowledge_links as lkl  # noqa: E402


class TestLintCaseKnowledgeLinks(unittest.TestCase):
    def test_resolve_knowledge_lint_merge(self) -> None:
        cfg = {"hydrodesk_shell": {"knowledge_lint": {"require_raw_dir": True}}}
        m = lkl.resolve_knowledge_lint(cfg)
        self.assertTrue(m["require_raw_dir"])
        self.assertIn("cases/{case_id}/manifest.yaml", m["required_paths"])

    def test_scan_markdown_broken_relative(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            md = ws / "a.md"
            md.write_text("broken [l](missing.md)\n", encoding="utf-8")
            rows = lkl.scan_markdown_links(ws, md)
            kinds = [r.get("kind") for r in rows]
            self.assertIn("broken_relative", kinds)

    def test_scan_markdown_ok_relative(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "t.md").write_text("x", encoding="utf-8")
            md = ws / "a.md"
            md.write_text("ok [l](./t.md)\n", encoding="utf-8")
            rows = lkl.scan_markdown_links(ws, md)
            self.assertTrue(any(r.get("kind") == "ok" for r in rows))

    def test_scan_skips_http(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            md = ws / "a.md"
            md.write_text("[u](https://example.com/x)\n", encoding="utf-8")
            self.assertEqual(lkl.scan_markdown_links(ws, md), [])


if __name__ == "__main__":
    unittest.main()
