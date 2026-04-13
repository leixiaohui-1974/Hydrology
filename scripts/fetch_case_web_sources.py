#!/usr/bin/env python3
"""Fetch web source seeds/discovered URLs into case-local downloads.

This is a generic case-level augmentation step:
- read URLs from cases/<case_id>/ingest/web/*.json
- download small text-like resources into ingest/web/downloads/
- write a contract-native fetch report under cases/<case_id>/contracts/
- refresh source/web session contracts by re-running import_case_sourcebundle

It does not hardcode any case-specific logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


WORKSPACE = Path(__file__).resolve().parents[2]
HYDROLOGY = WORKSPACE / "Hydrology"
if str(HYDROLOGY) not in sys.path:
    sys.path.insert(0, str(HYDROLOGY))

from workflows._shared import write_json  # noqa: E402
from import_case_sourcebundle import import_case_sourcebundle  # noqa: E402


TEXTUAL_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
)
DEFAULT_MAX_BYTES = 3 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path) -> str:
    return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()


def _web_root(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "ingest" / "web"


def _downloads_dir(case_id: str) -> Path:
    return _web_root(case_id) / "downloads"


def _contracts_dir(case_id: str) -> Path:
    return WORKSPACE / "cases" / case_id / "contracts"


def _fetch_report_path(case_id: str) -> Path:
    return _contracts_dir(case_id) / "web_fetch_report.latest.json"


def _iter_web_json_files(case_id: str) -> list[Path]:
    web_root = _web_root(case_id)
    if not web_root.exists():
        return []
    return [path.resolve() for path in sorted(web_root.glob("*.json")) if path.is_file()]


def _normalize_url_entry(raw: Any, source_file: Path, index: int) -> dict[str, Any] | None:
    if isinstance(raw, str):
        url = raw.strip()
        if not url:
            return None
        return {
            "id": f"{source_file.stem}-{index}",
            "url": url,
            "kind": source_file.stem,
            "title": None,
            "source_file": _workspace_rel(source_file),
        }
    if isinstance(raw, dict):
        url = str(raw.get("url") or "").strip()
        if not url:
            return None
        return {
            "id": str(raw.get("id") or f"{source_file.stem}-{index}"),
            "url": url,
            "kind": str(raw.get("kind") or source_file.stem),
            "title": raw.get("title"),
            "purpose": raw.get("purpose"),
            "notes": raw.get("notes"),
            "source_file": _workspace_rel(source_file),
        }
    return None


def _collect_url_entries(case_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _iter_web_json_files(case_id):
        payload = _safe_load_json(path)
        if isinstance(payload, dict):
            groups = []
            if isinstance(payload.get("urls"), list):
                groups.extend(payload["urls"])
            if isinstance(payload.get("sources"), list):
                groups.extend(payload["sources"])
            if isinstance(payload.get("queries"), list):
                continue
        elif isinstance(payload, list):
            groups = payload
        else:
            continue

        for idx, raw in enumerate(groups, start=1):
            item = _normalize_url_entry(raw, path, idx)
            if not item:
                continue
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            entries.append(item)
    return entries


def _guess_extension(content_type: str, url: str) -> str:
    lower = content_type.lower()
    if "json" in lower:
        return ".json"
    if "html" in lower:
        return ".html"
    if "xml" in lower:
        return ".xml"
    suffix = Path(urlparse(url).path).suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    return guessed or ".txt"


def _slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "resource"


def _download_target(case_id: str, item: dict[str, Any], content_type: str) -> Path:
    parsed = urlparse(item["url"])
    stem = _slugify(str(item.get("id") or Path(parsed.path).stem or parsed.netloc))
    digest = hashlib.sha1(item["url"].encode("utf-8")).hexdigest()[:10]
    ext = _guess_extension(content_type, item["url"])
    return _downloads_dir(case_id) / f"{stem}-{digest}{ext}"


def _is_textual(content_type: str) -> bool:
    lower = content_type.lower()
    return any(lower.startswith(prefix) for prefix in TEXTUAL_CONTENT_TYPES)


def _fetch_one(case_id: str, item: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    url = item["url"]
    request = Request(url, headers={"User-Agent": "HydroMind-WebFetch/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                return {
                    "url": url,
                    "status": "skipped_too_large",
                    "content_type": content_type,
                    "content_length": int(content_length),
                }
            if not _is_textual(content_type):
                return {
                    "url": url,
                    "status": "skipped_binary",
                    "content_type": content_type,
                    "content_length": int(content_length) if content_length else None,
                }
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return {
                    "url": url,
                    "status": "skipped_too_large",
                    "content_type": content_type,
                    "content_length": len(body),
                }
            target = _download_target(case_id, item, content_type)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            return {
                "url": url,
                "status": "downloaded",
                "content_type": content_type,
                "content_length": len(body),
                "path": _workspace_rel(target),
                "id": item.get("id"),
                "kind": item.get("kind"),
                "source_file": item.get("source_file"),
            }
    except HTTPError as error:
        return {"url": url, "status": "http_error", "http_status": error.code, "error": str(error)}
    except URLError as error:
        return {"url": url, "status": "network_error", "error": str(error)}
    except Exception as error:  # noqa: BLE001
        return {"url": url, "status": "error", "error": str(error)}


def fetch_case_web_sources(case_id: str, *, max_bytes: int = DEFAULT_MAX_BYTES, refresh_sourcebundle: bool = True) -> dict[str, Any]:
    entries = _collect_url_entries(case_id)
    downloads = [_fetch_one(case_id, item, max_bytes=max_bytes) for item in entries]
    downloaded = [row for row in downloads if row.get("status") == "downloaded"]
    report = {
        "case_id": case_id,
        "schema_version": "web_fetch_report.v1",
        "generated_at": _now_iso(),
        "web_root": _workspace_rel(_web_root(case_id)),
        "downloads_dir": _workspace_rel(_downloads_dir(case_id)),
        "seed_count": len(entries),
        "downloaded_count": len(downloaded),
        "results": downloads,
    }
    report_path = _fetch_report_path(case_id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, report)

    import_result = None
    if refresh_sourcebundle:
        import_result = import_case_sourcebundle(case_id)

    return {
        "ok": True,
        "case_id": case_id,
        "report_contract": _workspace_rel(report_path),
        "seed_count": len(entries),
        "downloaded_count": len(downloaded),
        "refresh_sourcebundle": refresh_sourcebundle,
        "sourcebundle_refresh_result": import_result,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch case-local web source seeds into ingest/web/downloads")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--no-refresh-sourcebundle", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = fetch_case_web_sources(
        args.case_id.strip(),
        max_bytes=int(args.max_bytes),
        refresh_sourcebundle=not args.no_refresh_sourcebundle,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
