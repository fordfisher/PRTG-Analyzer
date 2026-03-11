from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .core_log_parser import parse_core_log
from .erp_calculator import calculate_total_requests_per_min, refresh_rate_distribution
from .models import AnalysisResult, CoreLogResult
from .rules_engine import evaluate
from .timeline_analyzer import build_timeline
from .version import ANALYZER_VERSION


def run_analysis(core_log_path: str, status_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    core = parse_core_log(Path(core_log_path))
    result = evaluate(core)

    refresh = refresh_rate_distribution(core)
    timeline = build_timeline(core)

    data: Dict[str, Any] = {
        "core": core.model_dump(),
        "score": result.score,
        "findings": [f.model_dump() for f in result.findings],
        "refresh_rate_distribution": [asdict(b) for b in refresh],
        "calculated_requests_per_min": calculate_total_requests_per_min(core),
        "timeline": [asdict(p) for p in timeline],
        "metadata": {
            "analyzer_version": ANALYZER_VERSION,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if status_snapshot is not None:
        data["status_snapshot"] = status_snapshot
    return data


def _normalize_timeframe_count(core: Dict[str, Any], timeframe: Optional[str]) -> Optional[int]:
    if not timeframe or timeframe == "all":
        return None
    try:
        count = int(timeframe)
    except ValueError:
        return None
    if count < 1:
        return None
    segments = core.get("error_patterns_by_segment") or []
    if not segments:
        return None
    return min(count, len(segments))


def _aggregate_error_patterns(core: Dict[str, Any], timeframe: Optional[str], *, limit: int) -> list[Dict[str, Any]]:
    segments = core.get("error_patterns_by_segment") or []
    if not segments:
        fallback = core.get("top_errors") or []
        return [dict(item) for item in fallback[:limit]]

    count = _normalize_timeframe_count(core, timeframe) or len(segments)
    merged: Dict[str, Dict[str, Any]] = {}
    for seg_idx in range(count):
        for entry in segments[seg_idx] or []:
            pattern = entry.get("pattern", "")
            if pattern not in merged:
                merged[pattern] = {
                    "pattern": pattern,
                    "count": 0,
                    "first_seen": entry.get("first_seen", ""),
                    "last_seen": entry.get("last_seen", ""),
                    "sample_lines": [],
                }
            target = merged[pattern]
            target["count"] += int(entry.get("count", 0) or 0)
            first_seen = entry.get("first_seen") or ""
            last_seen = entry.get("last_seen") or ""
            if first_seen and (not target["first_seen"] or first_seen < target["first_seen"]):
                target["first_seen"] = first_seen
            if last_seen and (not target["last_seen"] or last_seen > target["last_seen"]):
                target["last_seen"] = last_seen
            for sample in (entry.get("sample_lines") or [])[:5]:
                if len(target["sample_lines"]) < 5:
                    target["sample_lines"].append(sample)

    return sorted(merged.values(), key=lambda item: item["count"], reverse=True)[:limit]


def aggregate_top_errors_for_timeframe(core: Dict[str, Any], timeframe: Optional[str], *, limit: int = 10) -> list[Dict[str, Any]]:
    merged = _aggregate_error_patterns(core, timeframe, limit=limit)
    return [
        dict(
            item,
            rank=index + 1,
            severity="warning" if item["count"] < 50 else "critical",
            explanation="",
        )
        for index, item in enumerate(merged)
    ]


def _window_start_for_count(core: Dict[str, Any], count: int) -> str:
    restarts = core.get("restart_events") or []
    if count <= 0:
        return core.get("first_timestamp") or ""
    if len(restarts) >= count:
        return str((restarts[-count] or {}).get("timestamp") or "")
    return core.get("first_timestamp") or ""


def _overlay_snapshot_fields(core: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    for key, value in snapshot.items():
        core[key] = deepcopy(value)


def _aggregate_distributions(snapshots: list, count: int) -> tuple:
    """Merge global_impact_distribution and interval_distribution across the first *count* snapshots."""
    merged_impact: Dict[str, Dict[str, Any]] = {}
    merged_interval: Dict[Any, Dict[str, Any]] = {}

    for idx in range(min(count, len(snapshots))):
        snap = snapshots[idx]

        for level, info in (snap.get("global_impact_distribution") or {}).items():
            if level not in merged_impact:
                merged_impact[level] = {"total": 0, "sensors": {}}
            merged_impact[level]["total"] += info.get("total", 0)
            for stype, scount in (info.get("sensors") or {}).items():
                merged_impact[level]["sensors"][stype] = merged_impact[level]["sensors"].get(stype, 0) + scount

        for interval_key, info in (snap.get("interval_distribution") or {}).items():
            if interval_key not in merged_interval:
                merged_interval[interval_key] = {"total": 0, "sensors": {}}
            merged_interval[interval_key]["total"] += info.get("total", 0)
            for stype, scount in (info.get("sensors") or {}).items():
                merged_interval[interval_key]["sensors"][stype] = merged_interval[interval_key]["sensors"].get(stype, 0) + scount

    return merged_impact, merged_interval


def _build_timeframed_core(core: Dict[str, Any], count: int) -> Dict[str, Any]:
    snapshots = core.get("segment_snapshots") or []
    active_snapshot_idx = min(max(count - 1, 0), len(snapshots) - 1) if snapshots else 0
    active_snapshot = snapshots[active_snapshot_idx] if snapshots else {}
    result_core = deepcopy(core)
    _overlay_snapshot_fields(result_core, active_snapshot)

    if snapshots:
        merged_impact, merged_interval = _aggregate_distributions(snapshots, count)
        result_core["global_impact_distribution"] = merged_impact
        result_core["interval_distribution"] = merged_interval

    err_per = core.get("errors_per_segment") or []
    warn_per = core.get("warnings_per_segment") or []
    total_restarts = len(core.get("restart_events") or [])
    timeframed_patterns = _aggregate_error_patterns(core, str(count), limit=500)
    window_start = _window_start_for_count(core, count)
    last_timestamp = core.get("last_timestamp") or ""
    first_timestamp = window_start or core.get("first_timestamp") or ""

    result_core["total_errors"] = sum(err_per[:count])
    result_core["total_warnings"] = sum(warn_per[:count])
    result_core["total_restarts"] = min(count, total_restarts)
    result_core["top_errors"] = aggregate_top_errors_for_timeframe(core, str(count), limit=10)
    result_core["error_patterns"] = [
        {
            "pattern": item["pattern"],
            "count": item["count"],
            "first_seen": item["first_seen"],
            "last_seen": item["last_seen"],
            "severity": "warning" if item["count"] < 50 else "critical",
        }
        for item in timeframed_patterns
    ]
    result_core["errors_since_last_restart"] = result_core["total_errors"]

    error_timestamps_by_segment = core.get("error_timestamps_by_segment") or []
    selected_error_timestamps = [
        timestamp
        for segment in error_timestamps_by_segment[:count]
        for timestamp in (segment or [])
        if timestamp
    ]
    if last_timestamp:
        try:
            cutoff_24h = (datetime.fromisoformat(last_timestamp.replace(" ", "T", 1)) - timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
        except ValueError:
            cutoff_24h = ""
    else:
        cutoff_24h = ""
    effective_cutoff = max(window_start, cutoff_24h) if cutoff_24h else window_start
    result_core["errors_last_24h"] = sum(1 for timestamp in selected_error_timestamps if timestamp >= effective_cutoff)

    selected_restart_events = (core.get("restart_events") or [])[-min(count, total_restarts) :] if total_restarts else []
    result_core["restart_events"] = deepcopy(selected_restart_events)
    result_core["startup_milestones"] = [
        deepcopy(milestone)
        for milestone in (core.get("startup_milestones") or [])
        if not window_start or str(milestone.get("timestamp") or "") >= window_start
    ]
    result_core["first_timestamp"] = first_timestamp
    result_core["last_timestamp"] = last_timestamp
    if first_timestamp and last_timestamp:
        try:
            start_dt = datetime.fromisoformat(first_timestamp.replace(" ", "T", 1))
            end_dt = datetime.fromisoformat(last_timestamp.replace(" ", "T", 1))
            result_core["log_span_days"] = (end_dt - start_dt).total_seconds() / 86400.0
        except ValueError:
            result_core["log_span_days"] = core.get("log_span_days", 0.0)
    else:
        result_core["log_span_days"] = 0.0
    return result_core


def apply_timeframe(data: Dict[str, Any], timeframe: Optional[str]) -> Dict[str, Any]:
    """Return a copy of result fully rebuilt for the given timeframe window."""
    if not timeframe or timeframe == "all":
        return data
    core = data.get("core") or {}
    k = _normalize_timeframe_count(core, timeframe)
    if k is None:
        return data

    result = deepcopy(data)
    result_core = _build_timeframed_core(core, k)
    core_model = CoreLogResult.model_validate(result_core)
    analysis: AnalysisResult = evaluate(core_model)

    result["core"] = core_model.model_dump()
    result["score"] = analysis.score
    result["findings"] = [f.model_dump() for f in analysis.findings]
    result["refresh_rate_distribution"] = [asdict(bucket) for bucket in refresh_rate_distribution(core_model)]
    result["calculated_requests_per_min"] = calculate_total_requests_per_min(core_model)
    result["timeline"] = [asdict(point) for point in build_timeline(core_model)]
    return result
