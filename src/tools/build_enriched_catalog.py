from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.config import CONFIG


COMPACT_ENDPOINT_KEYS = {
    "name",
    "url",
    "method",
    "description",
    "required_parameters",
    "optional_parameters",
}


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} is not a JSON object")
        rows.append(payload)
    return rows


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _toolbench_file(toolbench_root: Path, category: str, file_name: str) -> Path:
    return toolbench_root / category / file_name


def _load_tool_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"ToolBench file is not a JSON object: {path}")
    return payload


def _endpoint_matches(row: dict[str, Any], endpoint: dict[str, Any]) -> bool:
    row_name = _clean(row.get("name")).lower()
    row_url = _clean(row.get("url")).lower()
    row_method = _clean(row.get("method")).lower()
    endpoint_name = _clean(endpoint.get("name")).lower()
    endpoint_url = _clean(endpoint.get("url")).lower()
    endpoint_method = _clean(endpoint.get("method")).lower()

    if row_url and endpoint_url and row_url == endpoint_url:
        return not row_method or not endpoint_method or row_method == endpoint_method
    if row_name and endpoint_name and row_name == endpoint_name:
        return not row_method or not endpoint_method or row_method == endpoint_method
    return False


def _find_endpoint(row: dict[str, Any], tool_payload: dict[str, Any]) -> dict[str, Any] | None:
    endpoints = tool_payload.get("api_list")
    if not isinstance(endpoints, list):
        return None
    for endpoint in endpoints:
        if isinstance(endpoint, dict) and _endpoint_matches(row, endpoint):
            return endpoint
    return None


def _compact_parameters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                key: item[key]
                for key in ("name", "description", "type", "default", "required")
                if key in item and item[key] not in (None, "")
            }
        )
    return compact


def _compact_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    compact = {key: endpoint[key] for key in COMPACT_ENDPOINT_KEYS if key in endpoint and endpoint[key] not in (None, "")}
    compact["required_parameters"] = _compact_parameters(endpoint.get("required_parameters"))
    compact["optional_parameters"] = _compact_parameters(endpoint.get("optional_parameters"))
    return compact


def _enrich_row(row: dict[str, Any], *, toolbench_root: Path) -> tuple[dict[str, Any], bool, bool]:
    enriched = dict(row)
    category = _clean(row.get("category"))
    file_name = _clean(row.get("_file") or row.get("file_name"))
    tool_path = _toolbench_file(toolbench_root, category, file_name) if category and file_name else Path()
    tool_payload = _load_tool_file(tool_path) if category and file_name else None
    tool_found = tool_payload is not None
    endpoint = _find_endpoint(row, tool_payload) if tool_payload is not None else None
    endpoint_found = endpoint is not None

    enrichment = {
        "status": "matched" if endpoint_found else ("tool_file_found" if tool_found else "tool_file_missing"),
        "tool_file_found": tool_found,
        "endpoint_found": endpoint_found,
        "file_name": file_name,
        "toolbench_relative_path": str(Path(category) / file_name) if category and file_name else "",
    }
    if tool_payload is not None:
        enrichment["tool_name"] = _clean(tool_payload.get("tool_name") or tool_payload.get("name") or tool_payload.get("title"))
        enrichment["tool_description"] = _clean(tool_payload.get("tool_description") or tool_payload.get("description"))

    if endpoint is not None:
        compact_endpoint = _compact_endpoint(endpoint)
        enriched["toolbench_tool_name"] = enrichment.get("tool_name", "")
        enriched["toolbench_tool_description"] = enrichment.get("tool_description", "")
        enriched["toolbench_endpoint_description"] = _clean(compact_endpoint.get("description"))
        enriched["toolbench_endpoint_details"] = {
            "required_parameters": compact_endpoint.get("required_parameters", []),
            "optional_parameters": compact_endpoint.get("optional_parameters", []),
        }
        enriched["endpoint_details"] = enriched["toolbench_endpoint_details"]
        enrichment.update(
            {
                "endpoint_name": _clean(compact_endpoint.get("name")),
                "endpoint_method": _clean(compact_endpoint.get("method")),
                "endpoint_url": _clean(compact_endpoint.get("url")),
                "endpoint_description": _clean(compact_endpoint.get("description")),
                "endpoint_details": enriched["endpoint_details"],
            }
        )

    enriched["toolbench_enrichment"] = enrichment
    return enriched, tool_found, endpoint_found


def build_enriched_catalog(
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    toolbench_root: str | Path,
) -> dict[str, int]:
    input_file = Path(input_path or CONFIG.catalog_path).expanduser()
    output_file = Path(output_path or CONFIG.catalog_enriched_path).expanduser()
    toolbench_root = Path(toolbench_root).expanduser()
    rows = _iter_jsonl(input_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    tool_files_found = 0
    endpoints_found = 0
    with output_file.open("w", encoding="utf-8") as handle:
        for row in rows:
            enriched, tool_found, endpoint_found = _enrich_row(row, toolbench_root=toolbench_root)
            tool_files_found += int(tool_found)
            endpoints_found += int(endpoint_found)
            handle.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n")

    return {
        "records": len(rows),
        "tool_file_found": tool_files_found,
        "endpoint_found": endpoints_found,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize compact ToolBench endpoint evidence into the API catalog.")
    parser.add_argument("--input", type=Path, default=CONFIG.catalog_path)
    parser.add_argument("--output", type=Path, default=CONFIG.catalog_enriched_path)
    parser.add_argument("--toolbench-root", type=Path, required=True)
    args = parser.parse_args()

    summary = build_enriched_catalog(args.input, args.output, toolbench_root=args.toolbench_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

