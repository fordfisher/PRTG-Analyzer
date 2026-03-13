from __future__ import annotations

from copy import deepcopy
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import CoreLogResult

TECH_BREAKDOWN_RE = re.compile(r"(\d+)x\s*([\w.-]+)")
RESTART_MARKER_RE = re.compile(r"Logger initialized", re.IGNORECASE)
BRACED_GUID_RE = re.compile(
    r"\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}",
    re.IGNORECASE,
)
GUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


@dataclass
class _PatternAgg:
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_lines: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.sample_lines is None:
            self.sample_lines = []


@dataclass(slots=True)
class _ErrorOccurrence:
    ts_str: str
    ts: Optional[datetime]
    pattern: str
    sample_line: str


@dataclass(slots=True)
class _WarningOccurrence:
    ts_str: str


def _parse_int(s: str) -> int:
    return int(s.replace(",", "").strip())


def _merge_counts(dst: Dict[str, int], src: Dict[str, int]) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def _parse_tech_breakdown(text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for match in TECH_BREAKDOWN_RE.finditer(text):
        out[match.group(2)] = out.get(match.group(2), 0) + int(match.group(1))
    return out


def _normalize_impact_label(raw: str) -> str:
    value = raw.strip().lower()
    if value.startswith("very low"):
        return "Very low"
    if value.startswith("very high"):
        return "Very High"
    if value.startswith("low"):
        return "Low"
    if value.startswith("medium"):
        return "Medium"
    if value.startswith("high"):
        return "High"
    return raw.strip().capitalize()


def _parse_ts(ts_str: str) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        normalized = ts_str.replace(" ", "T", 1)
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _normalize_error_text(text: str) -> str:
    normalized = BRACED_GUID_RE.sub("{<guid>}", text)
    normalized = GUID_RE.sub("<guid>", normalized)
    normalized = re.sub(r"\bTId\s+\d+\b", "TId <id>", normalized)
    normalized = re.sub(r"\b0x[0-9a-fA-F]+\b", "0x<hex>", normalized)
    normalized = re.sub(r"\b\d{2,}\b", "<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_restart_marker(line: str) -> bool:
    return "Logger initialized" in line and RESTART_MARKER_RE.search(line) is not None


def _is_ignorable_license_message(message: str) -> bool:
    lower = message.lower()
    return "license" in lower or "activation" in lower or "license check" in lower


_SEGMENT_SNAPSHOT_FIELDS = (
    "server_name",
    "prtg_version",
    "license_owner",
    "license_key",
    "edition_type",
    "commercial_days_left",
    "max_sensors",
    "system_id",
    "os_version",
    "cpu_count",
    "cpu_model",
    "cpu_speed_ghz",
    "cpu_splitting_active",
    "cpu_assigned",
    "cpu_total_for_splitting",
    "process_mask",
    "system_mask",
    "total_ram_mb",
    "free_ram_mb",
    "total_pagefile_mb",
    "free_pagefile_mb",
    "data_path",
    "system_path",
    "storage_device",
    "timezone",
    "memory_manager",
    "installed_date",
    "created_date",
    "license_date",
    "total_sensors",
    "total_probes",
    "total_devices",
    "total_groups",
    "total_channels",
    "total_users",
    "probes",
    "global_impact_distribution",
    "sensor_technologies",
    "interval_distribution",
    "thread_stats",
    "max_thread_runtime",
    "long_running_threads",
    "total_erp",
    "estimated_requests_per_second",
    "sensors_exceeding_50_channels",
)


def _snapshot_from_result(core: CoreLogResult) -> Dict[str, Any]:
    return {field: deepcopy(getattr(core, field)) for field in _SEGMENT_SNAPSHOT_FIELDS}


def _copy_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(snapshot)


def _finalize_snapshot(snapshot: Dict[str, Any]) -> None:
    probes = snapshot.get("probes") or []
    snapshot["probes"] = sorted(probes, key=lambda probe: int(probe.get("sensor_count") or 0), reverse=True)
    thread_stats = snapshot.get("thread_stats") or []
    snapshot["long_running_threads"] = [stat for stat in thread_stats if float(stat.get("runtime_sec") or 0.0) > 120.0]


def _get_or_create_probe_snapshot(snapshot: Dict[str, Any], probe_id: int, probe_name: str) -> Dict[str, Any]:
    probes = snapshot.setdefault("probes", [])
    for probe in probes:
        if int(probe.get("probe_id") or -1) == probe_id:
            if probe_name:
                probe["name"] = probe_name
            return probe

    probe = {
        "probe_id": probe_id,
        "name": probe_name,
        "sensor_count": 0,
        "erp": None,
        "technologies": {},
        "impact_distribution": {},
    }
    probes.append(probe)
    return probe
