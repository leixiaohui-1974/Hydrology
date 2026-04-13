#!/usr/bin/env python3
"""探源 (TanYuan) — Extract reusable public-data inventory from case web artifacts."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PUBLIC_DATA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dem": ("dem", "digital elevation", "elevation model", "topography", "terrain"),
    "landuse": ("landuse", "land cover", "landcover", "lulc", "copernicus land"),
    "soil": ("soil", "soilgrids", "pedology", "soil map"),
    "hydrography": ("hydrography", "hydrosheds", "hydrorivers", "river network", "basin"),
    "project_context": ("hydropower", "project", "station", "cascade", "construction"),
}
TEXT_SUFFIXES = {".html", ".htm", ".txt", ".md", ".json", ".xml"}
TEXT_LIMIT_BYTES = 256 * 1024
PROVIDER_HINTS: dict[str, tuple[str, ...]] = {
    "OpenTopography": ("opentopography.org", "opentopography"),
    "Copernicus": ("copernicus.eu", "copernicus"),
    "HydroSHEDS / WWF": ("worldwildlife.org", "hydrosheds", "world wildlife fund"),
}
LICENSE_HINTS = ("license", "licence", "copyright", "terms of use", "attribution")
AUTH_HINTS = ("api key", "token", "sign in", "log in", "authentication", "account")
RATE_LIMIT_HINTS = ("rate limit", "requests per", "quota", "throttle")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return " ".join(self._chunks)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def _read_text_excerpt(path: Path) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        raw = path.read_bytes()[:TEXT_LIMIT_BYTES]
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_title(text: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())
    return title or None


def _extract_meta_description(text: str) -> str | None:
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())
            if value:
                return value
    return None


def _plain_text_preview(text: str) -> str | None:
    lowered = text.lstrip().lower()
    if lowered.startswith("<!doctype html") or "<html" in lowered[:400]:
        parser = _HTMLTextExtractor()
        try:
            parser.feed(text)
            extracted = parser.text()
        except Exception:
            extracted = re.sub(r"<[^>]+>", " ", text)
    else:
        extracted = text
    preview = re.sub(r"\s+", " ", extracted).strip()
    if not preview:
        return None
    return preview[:400]


def _keyword_types(*texts: str) -> list[str]:
    haystack = " ".join(text for text in texts if text).lower()
    found: list[str] = []
    for data_type, keywords in PUBLIC_DATA_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            found.append(data_type)
    return found


def _provider_name(url: str, *texts: str) -> str | None:
    haystack = " ".join(text for text in texts if text).lower()
    netloc = urlparse(url).netloc.lower()
    provider_haystack = " ".join([netloc, haystack]).strip()
    for provider, hints in PROVIDER_HINTS.items():
        if any(hint in provider_haystack for hint in hints):
            return provider
    if not netloc:
        return None
    host = netloc.split("@")[-1].split(":")[0]
    labels = [label for label in host.split(".") if label and label not in {"www", "m"}]
    if not labels:
        return host or None
    primary = labels[-2] if len(labels) >= 2 else labels[0]
    return primary.replace("-", " ").title()


def _detect_hint(kind: str, text: str, keywords: tuple[str, ...]) -> str | None:
    haystack = " ".join(part for part in (kind, text) if part).lower()
    for keyword in keywords:
        if keyword in haystack:
            return keyword
    return None


def _collect_seed_metadata(case_id: str, workspace: Path) -> dict[str, dict[str, Any]]:
    web_root = workspace / "cases" / case_id / "ingest" / "web"
    metadata_by_url: dict[str, dict[str, Any]] = {}
    if not web_root.exists():
        return metadata_by_url
    for path in sorted(web_root.glob("*.json")):
        payload = _safe_load_json(path)
        groups: list[Any] = []
        if isinstance(payload, dict):
            for key in ("urls", "sources", "queries"):
                value = payload.get(key)
                if isinstance(value, list):
                    groups.extend(value)
        elif isinstance(payload, list):
            groups.extend(payload)
        for index, raw in enumerate(groups, start=1):
            if isinstance(raw, str):
                url = raw.strip()
                if not url:
                    continue
                metadata_by_url.setdefault(
                    url,
                    {
                        "id": f"{path.stem}-{index}",
                        "kind": path.stem,
                        "source_file": _workspace_rel(path, workspace),
                    },
                )
                continue
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if not url:
                continue
            entry = metadata_by_url.setdefault(url, {})
            entry.update(
                {
                    "id": str(raw.get("id") or entry.get("id") or f"{path.stem}-{index}"),
                    "kind": str(raw.get("kind") or entry.get("kind") or path.stem),
                    "title": raw.get("title") or entry.get("title"),
                    "purpose": raw.get("purpose") or entry.get("purpose"),
                    "notes": raw.get("notes") or entry.get("notes"),
                    "query": raw.get("query") or entry.get("query"),
                    "source_file": entry.get("source_file") or _workspace_rel(path, workspace),
                }
            )
    return metadata_by_url


def build_public_data_inventory(case_id: str, workspace: Path) -> dict[str, Any] | None:
    contracts_dir = workspace / "cases" / case_id / "contracts"
    fetch_report_path = contracts_dir / "web_fetch_report.latest.json"
    fetch_report = _safe_load_json(fetch_report_path)
    if not isinstance(fetch_report, dict):
        return None

    seed_metadata = _collect_seed_metadata(case_id, workspace)
    records: list[dict[str, Any]] = []
    blocked_sources: list[dict[str, Any]] = []
    available_public_data: set[str] = set()
    blocked_public_data: set[str] = set()
    status_counts: dict[str, int] = {}
    extraction_warnings: list[str] = []
    downloads_dir = workspace / "cases" / case_id / "ingest" / "web" / "downloads"
    web_source_session_path = workspace / "cases" / case_id / "contracts" / "web_source_session.latest.json"

    for index, row in enumerate(fetch_report.get("results") or [], start=1):
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        seed = seed_metadata.get(url) or {}
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        local_path: str | None = row.get("path")
        excerpt = None
        page_title = row.get("title") or seed.get("title")
        page_summary = row.get("summary") or seed.get("notes") or seed.get("purpose")
        artifact_type = "remote_url"
        path_exists = False
        if local_path:
            path = workspace / local_path
            artifact_type = path.suffix.lower().lstrip(".") or "file"
            path_exists = path.exists()
            text = _read_text_excerpt(path)
            if text:
                page_title = page_title or _extract_title(text)
                page_summary = page_summary or _extract_meta_description(text) or _plain_text_preview(text)
                excerpt = _plain_text_preview(text)
            elif not path_exists:
                extraction_warnings.append(f"missing_download:{local_path}")

        detected_public_data = _keyword_types(
            str(seed.get("kind") or row.get("kind") or ""),
            str(page_title or ""),
            str(page_summary or ""),
            str(seed.get("purpose") or ""),
            str(seed.get("notes") or ""),
            str(seed.get("query") or ""),
            str(excerpt or ""),
        )
        if status == "downloaded":
            available_public_data.update(detected_public_data)
        else:
            blocked_public_data.update(detected_public_data)
        provider = _provider_name(
            url,
            str(page_title or ""),
            str(page_summary or ""),
            str(seed.get("notes") or ""),
            str(seed.get("purpose") or ""),
        )
        combined_text = " ".join(
            str(part or "")
            for part in (
                page_title,
                page_summary,
                seed.get("notes"),
                seed.get("purpose"),
                excerpt,
            )
        )
        license_hint = _detect_hint(str(row.get("kind") or seed.get("kind") or ""), combined_text, LICENSE_HINTS)
        auth_hint = _detect_hint(str(row.get("kind") or seed.get("kind") or ""), combined_text, AUTH_HINTS)
        rate_limit_hint = _detect_hint(str(row.get("kind") or seed.get("kind") or ""), combined_text, RATE_LIMIT_HINTS)
        public_data_kind: str | None = None
        for preferred in ("dem", "landuse", "soil", "hydrography"):
            if preferred in detected_public_data:
                public_data_kind = preferred
                break
        if public_data_kind is None and detected_public_data:
            public_data_kind = detected_public_data[0]

        source_id = str(row.get("id") or seed.get("id") or f"result-{index}")
        priority_hint = "required" if public_data_kind in {"dem", "landuse", "soil", "hydrography"} else "context"
        record = {
            "source_id": source_id,
            "role": "downloaded_page" if status == "downloaded" else "blocked_web_source",
            "path": local_path,
            "artifact_type": artifact_type,
            "origin": "web_fetch_report",
            "discovered_by": row.get("source_file") or seed.get("source_file"),
            "exists": path_exists,
            "priority_hint": priority_hint,
            "url": url,
            "source_kind": row.get("kind") or seed.get("kind"),
            "public_data_kind": public_data_kind,
            "provider": provider,
            "title": page_title,
            "signals": {
                "fetch_status": status,
                "content_type": row.get("content_type"),
                "http_status": row.get("http_status"),
                "access_signal": "public_downloaded" if status == "downloaded" else "blocked_or_unknown",
                "license_hint": license_hint,
                "auth_hint": auth_hint,
                "rate_limit_hint": rate_limit_hint,
                "detected_public_data_kinds": detected_public_data,
            },
            "evidence": [
                {
                    "kind": "title",
                    "value": page_title,
                },
                {
                    "kind": "summary",
                    "value": page_summary,
                },
                {
                    "kind": "excerpt",
                    "value": excerpt,
                },
            ],
            "needs_review": not bool(public_data_kind),
            "confidence": 0.85 if public_data_kind else 0.6,
        }
        if record["needs_review"]:
            extraction_warnings.append(f"missing_public_data_kind:{source_id}")
        records.append(record)
        if status != "downloaded":
            blocked_sources.append(record)

    downloaded_items = [record for record in records if record.get("signals", {}).get("fetch_status") == "downloaded"]
    return {
        "case_id": case_id,
        "schema_version": "public_data_inventory.v1",
        "generated_at": _now_iso(),
        "downloads_dir": _workspace_rel(downloads_dir, workspace),
        "fetch_report_contract": _workspace_rel(fetch_report_path, workspace),
        "web_source_session_contract": _workspace_rel(web_source_session_path, workspace),
        "summary": {
            "record_count": len(records),
            "downloaded_count": len(downloaded_items),
            "blocked_count": len(blocked_sources),
            "available_public_data_kinds": sorted(available_public_data),
            "blocked_public_data_kinds": sorted(blocked_public_data - available_public_data),
            "status_counts": status_counts,
        },
        "records": records,
        "blocked_sources": blocked_sources,
        "extraction_warnings": sorted(set(extraction_warnings)),
    }
