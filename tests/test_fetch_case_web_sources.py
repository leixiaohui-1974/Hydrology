import json
from pathlib import Path
from typing import Optional

import fetch_case_web_sources as target


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8", content_length: Optional[int] = None):
        self._body = body
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(content_length if content_length is not None else len(body)),
        }

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_case_web_sources_downloads_text_resources_and_refreshes_sourcebundle(tmp_path: Path, monkeypatch) -> None:
    case_id = "demo_case"
    web_dir = tmp_path / "cases" / case_id / "ingest" / "web"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    web_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "seed_urls.json").write_text(
        json.dumps(
            {
                "urls": [
                    {"id": "project-page", "url": "https://example.com/project", "kind": "project_context"},
                    {"id": "metadata", "url": "https://example.com/metadata.json", "kind": "catalog"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    refresh_calls: list[str] = []

    def _fake_urlopen(request, timeout=20):  # noqa: ANN001
        if request.full_url.endswith("/metadata.json"):
            return _FakeResponse(b'{"ok": true}', "application/json")
        return _FakeResponse(b"<html>demo</html>", "text/html; charset=utf-8")

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        target,
        "import_case_sourcebundle",
        lambda requested_case_id: refresh_calls.append(requested_case_id) or {"ok": True, "case_id": requested_case_id},
    )

    payload = target.fetch_case_web_sources(case_id)
    report_path = contracts_dir / "web_fetch_report.latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert refresh_calls == [case_id]
    assert payload["ok"] is True
    assert payload["report_contract"] == f"cases/{case_id}/contracts/web_fetch_report.latest.json"
    assert payload["downloaded_count"] == 2
    assert report["downloads_dir"] == f"cases/{case_id}/ingest/web/downloads"
    assert report["seed_count"] == 2
    assert report["downloaded_count"] == 2
    assert [row["status"] for row in report["results"]] == ["downloaded", "downloaded"]

    downloaded_paths = [tmp_path / row["path"] for row in report["results"]]
    assert all(path.exists() for path in downloaded_paths)
    assert downloaded_paths[0].read_text(encoding="utf-8") == "<html>demo</html>"
    assert json.loads(downloaded_paths[1].read_text(encoding="utf-8")) == {"ok": True}


def test_fetch_case_web_sources_skips_refresh_when_disabled_and_records_non_download_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_id = "demo_case"
    web_dir = tmp_path / "cases" / case_id / "ingest" / "web"
    contracts_dir = tmp_path / "cases" / case_id / "contracts"
    web_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "seed_urls.json").write_text(
        json.dumps(
            {
                "urls": [
                    {"id": "binary", "url": "https://example.com/map.tif", "kind": "dem_catalog"},
                    {"id": "huge", "url": "https://example.com/big.html", "kind": "document"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _fake_urlopen(request, timeout=20):  # noqa: ANN001
        if request.full_url.endswith("/map.tif"):
            return _FakeResponse(b"binary-data", "application/octet-stream")
        return _FakeResponse(b"<html>too large</html>", content_length=1024)

    monkeypatch.setattr(target, "WORKSPACE", tmp_path)
    monkeypatch.setattr(target, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        target,
        "import_case_sourcebundle",
        lambda requested_case_id: (_ for _ in ()).throw(AssertionError(f"refresh should not run for {requested_case_id}")),
    )

    payload = target.fetch_case_web_sources(case_id, max_bytes=64, refresh_sourcebundle=False)
    report = json.loads((contracts_dir / "web_fetch_report.latest.json").read_text(encoding="utf-8"))

    assert payload["refresh_sourcebundle"] is False
    assert payload["sourcebundle_refresh_result"] is None
    assert payload["downloaded_count"] == 0
    assert report["downloaded_count"] == 0
    assert [row["status"] for row in report["results"]] == ["skipped_binary", "skipped_too_large"]
    assert not (web_dir / "downloads").exists()
