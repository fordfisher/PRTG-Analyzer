from __future__ import annotations

from typing import Any, Dict, Optional


def parse_csv_param(value: Optional[str]) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def parse_csv_int_param(value: Optional[str]) -> Optional[list[int]]:
    if value is None:
        return None
    parts = parse_csv_param(value)
    try:
        return [int(item) for item in parts]
    except ValueError:
        return []


def filter_export_errors(result: Dict[str, Any], patterns_csv: Optional[str]) -> Dict[str, Any]:
    patterns = parse_csv_param(patterns_csv)
    if not patterns or not isinstance(result, dict) or not isinstance(result.get("core"), dict):
        return result
    core = dict(result["core"])
    top = core.get("top_errors") or []
    if isinstance(top, list):
        wanted = set(patterns)
        core["top_errors"] = [entry for entry in top if str(entry.get("pattern", "")) in wanted]
    filtered = dict(result)
    filtered["core"] = core
    return filtered
