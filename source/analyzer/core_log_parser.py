from __future__ import annotations

from bisect import bisect_right
import gzip
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .core_log_parser_helpers import (
    _copy_snapshot,
    _ErrorOccurrence,
    _finalize_snapshot,
    _get_or_create_probe_snapshot,
    _is_ignorable_license_message,
    _is_restart_marker,
    _merge_counts,
    _normalize_error_text,
    _normalize_impact_label,
    _parse_int,
    _parse_tech_breakdown,
    _parse_ts,
    _PatternAgg,
    _snapshot_from_result,
    _WarningOccurrence,
)
from .models import (
    CoreLogResult,
    ErrorDetail,
    ErrorPattern,
    ImpactLevel,
    IntervalInfo,
    Milestone,
    ProbeInfo,
    RestartEvent,
    ThreadStat,
)


LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+(INFO|WARN|ERRR)\s+TId\s+(\d+)\s+(\w+)>\s*(.*)"
)

SERVER_RE = re.compile(
    r'PRTG Network Monitor ([\d.]+)\s.*?(?:core server|Core Server)\s+(?:starting|start)\w*\s+on\s+"([^"]+)"'
)
LICENSE_RE = re.compile(r'licensed for "([^"]+)"\s*\(([^)]+)\)\s*Edt=(\d+),MaxS=(\d+)')
DAYS_LEFT_RE = re.compile(r"Version:\s*(\S+)\s+Days left:\s*(-?\d+)")
OS_RE = re.compile(
    r'OS:\s*(Microsoft Windows Server \d{4}[^,]*),\s*(\d+)\s+CPUs?\s+\(([^)]+)\).*?on\s+"([^"]+)"'
)
CPU_SPEED_RE = re.compile(r"Current max\.\s*CPU speed\s*([\d.]+)\s*GHz")
MEM_RE = re.compile(
    r"Free Physical:\s*([\d,]+)\s*MB.*?Total Physical:\s*([\d,]+)\s*MB.*?Free Pagefile:\s*([\d,]+)\s*MB.*?Total Pagefile:\s*([\d,]+)\s*MB"
)
PATH_RE = re.compile(r"Startup:\s*(Data|System) path:\s*(.+?)\\?\s*$")
MM_RE = re.compile(r"Memory manager:\s*(\S+)")
TZ_RE = re.compile(r"System time zone:\s*(.+)")
OBJECTS_RE = re.compile(r"Objects:\s*(.+)")
OBJECT_ITEM_RE = re.compile(r"(\d+)x\s+([^,]+?)(?:,|$)")

SENSORS_ON_PROBE_RE = re.compile(
    r"Startup:\s*Sensors on Probe ID (\d+)\s+(.*?)\s+\((\d+)\s+Sensors total(?:\s*-\s*erps:\s*([\d.]+))?\)\s*(.*)$"
)
SENSORS_ON_PROBEID_RE = re.compile(
    r'Startup:\s*Sensors on ProbeId (\d+)\s+"([^"]+)"\s+\((\d+)\s+Sensors total\)'
)

IMPACT_RE = re.compile(r"Sensors \((\w[\w\s]+?) impact on system performance - (\d+) Sensors total\):\s*(.*)")
SUMMARY_START_RE = re.compile(r'Startup:\s*Sensors for "summary"\s*\((\d+)\s+Sensors total\)')

INTERVAL_RE = re.compile(r"Sensors with Interval of (\d+) Seconds \((\d+) Sensors total\):\s*(.*)")
EST_RPS_RE = re.compile(r"Estimated overall monitoring requests per second:\s*([\d.]+)")

THREAD_RE = re.compile(r"([\w()]+(?:\s*\(\d+\))?(?:\s+\d+)?)\s+#\d+\s+([\d.]+)\s+sec\s+(Running|Waiting|Stopped)")

SENSORS_50_CH_RE = re.compile(r"Sensors that exceed 50 channels:\s*\((\d+)\s+total\)\s*(.*)")
INSTALL_DATES_RE = re.compile(
    r"Installed:\s*([\d-]+\s+[\d:]+)\s+Created:\s*([\d-]+\s+[\d:]+)\s+License:\s*([\d-]+\s+[\d:]+)"
)
SPLITTED_CPU_RE = re.compile(
    r"Running PRTG core server on splitted CPU settings\s*\((\d+)/(\d+)\)"
)
PROCESSMASK_RE = re.compile(r"Processmask:\s*(.+)")
SYSTEMMASK_RE = re.compile(r"Systemmask:\s*(.+)")
SYSTEMID_RE = re.compile(r"System\s*ID\s*:\s*(.+)", re.IGNORECASE)
ACTIVATION_SYSTEMID_RE = re.compile(r"Activation(?:Code)?\s*:\s*(SYSTEMID-[A-Z0-9\-]+)", re.IGNORECASE)


def _open_text_stream(path: Path) -> Tuple[Iterable[str], str]:
    """
    Return an iterable of text lines and the chosen encoding label.
    Supports .gz.
    """
    if path.suffix.lower() == ".gz":
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                # test decode by reading a small chunk
                with gzip.open(path, "rt", encoding=enc, errors="strict") as f_test:
                    f_test.read(4096)
                return gzip.open(path, "rt", encoding=enc, errors="replace"), enc
            except UnicodeDecodeError:
                continue
        return gzip.open(path, "rt", encoding="latin-1", errors="replace"), "latin-1"

    # Non-gz: try encodings with streaming read
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            f = path.open("r", encoding=enc, errors="strict")
            # probe first chunk
            f.read(4096)
            f.seek(0)
            return f, enc
        except UnicodeDecodeError:
            continue

    return path.open("r", encoding="latin-1", errors="replace"), "latin-1"


def parse_core_log(path: Path) -> CoreLogResult:
    stream, _enc = _open_text_stream(path)

    res = CoreLogResult()
    probes_by_id: Dict[int, ProbeInfo] = {}
    current_probe: Optional[ProbeInfo] = None
    in_global_summary = False
    segment_snapshots_forward: List[Dict[str, Any]] = []
    current_snapshot: Optional[Dict[str, Any]] = None
    segment_probe_summary_reset = False
    segment_global_impact_reset = False
    segment_interval_reset = False
    segment_thread_reset = False
    segment_probe_impact_reset: set[int] = set()

    patterns: Dict[str, _PatternAgg] = {}
    error_occurrences: List[_ErrorOccurrence] = []
    warning_occurrences: List[_WarningOccurrence] = []
    warn_count = 0
    err_count = 0

    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    max_ts: Optional[datetime] = None
    milestones: List[Milestone] = []

    def _start_new_segment() -> None:
        nonlocal current_snapshot
        nonlocal segment_probe_summary_reset
        nonlocal segment_global_impact_reset
        nonlocal segment_interval_reset
        nonlocal segment_thread_reset
        nonlocal segment_probe_impact_reset

        if current_snapshot is not None:
            _finalize_snapshot(current_snapshot)
            segment_snapshots_forward.append(current_snapshot)

        base = current_snapshot if current_snapshot is not None else _snapshot_from_result(res)
        current_snapshot = _copy_snapshot(base)
        # Do not carry over segment-specific data; each segment gets data only from its own log block.
        current_snapshot["global_impact_distribution"] = {}
        current_snapshot["interval_distribution"] = {}
        current_snapshot["probes"] = []
        segment_probe_summary_reset = False
        segment_global_impact_reset = False
        segment_interval_reset = False
        segment_thread_reset = False
        segment_probe_impact_reset = set()

    try:
        for raw_line in stream:
            line = raw_line.rstrip("\n")

            m = LINE_RE.match(line)
            ts_str: Optional[str] = None
            level: Optional[str] = None
            msg = line
            ts: Optional[datetime] = None

            if m:
                ts_str = m.group(1)
                level = m.group(2)
                msg = m.group(5)
                ts = _parse_ts(ts_str)
                if ts is not None:
                    if first_ts is None:
                        first_ts = ts
                        res.first_timestamp = ts_str
                    last_ts = ts
                    res.last_timestamp = ts_str
                    max_ts = ts if max_ts is None else max(max_ts, ts)

            is_restart_marker = _is_restart_marker(line)
            if current_snapshot is None or is_restart_marker:
                _start_new_segment()

            if is_restart_marker:
                if ts_str:
                    res.restart_events.append(RestartEvent(timestamp=ts_str))
                    res.total_restarts = len(res.restart_events)
                milestones.append(Milestone(name="Logger initialized", timestamp=ts_str or ""))

            if "PRTG Network Monitor" in line:
                sm = SERVER_RE.search(line)
                if sm:
                    res.prtg_version = sm.group(1)
                    res.server_name = sm.group(2)
                    current_snapshot["prtg_version"] = res.prtg_version
                    current_snapshot["server_name"] = res.server_name

            if "licensed for" in line:
                lm = LICENSE_RE.search(line)
                if lm:
                    res.license_owner = lm.group(1)
                    res.license_key = lm.group(2)
                    res.max_sensors = int(lm.group(4))
                    current_snapshot["license_owner"] = res.license_owner
                    current_snapshot["license_key"] = res.license_key
                    current_snapshot["max_sensors"] = res.max_sensors

            if "Days left:" in line:
                dlm = DAYS_LEFT_RE.search(line)
                if dlm:
                    try:
                        res.commercial_days_left = int(dlm.group(2))
                        current_snapshot["commercial_days_left"] = res.commercial_days_left
                    except ValueError:
                        pass

            if "Startup:" in line:
                om = OS_RE.search(line)
                if om:
                    res.os_version = om.group(1)
                    res.cpu_count = int(om.group(2))
                    res.cpu_model = om.group(3)
                    res.storage_device = om.group(4)
                    current_snapshot["os_version"] = res.os_version
                    current_snapshot["cpu_count"] = res.cpu_count
                    current_snapshot["cpu_model"] = res.cpu_model
                    current_snapshot["storage_device"] = res.storage_device

                pm = PATH_RE.search(line)
                if pm:
                    kind = pm.group(1).lower()
                    val = pm.group(2).strip()
                    if kind == "data":
                        res.data_path = val
                        current_snapshot["data_path"] = val
                    else:
                        res.system_path = val
                        current_snapshot["system_path"] = val

                p1 = SENSORS_ON_PROBE_RE.search(line)
                if p1:
                    probe_id = int(p1.group(1))
                    probe_name = p1.group(2).strip()
                    total = int(p1.group(3))
                    erp = float(p1.group(4)) if p1.group(4) else None
                    tech = _parse_tech_breakdown(p1.group(5) or "")

                    probe = probes_by_id.get(probe_id)
                    if probe is None:
                        probe = ProbeInfo(probe_id=probe_id, name=probe_name, sensor_count=total, erp=erp)
                        probes_by_id[probe_id] = probe
                    else:
                        probe.name = probe_name or probe.name
                        probe.sensor_count = total or probe.sensor_count
                        probe.erp = erp if erp is not None else probe.erp

                    if not segment_probe_summary_reset:
                        current_snapshot["probes"] = []
                        current_snapshot["sensor_technologies"] = {}
                        segment_probe_summary_reset = True
                    _merge_counts(probe.technologies, tech)
                    _merge_counts(res.sensor_technologies, tech)
                    probe_snapshot = _get_or_create_probe_snapshot(current_snapshot, probe_id, probe_name)
                    probe_snapshot["sensor_count"] = total
                    probe_snapshot["erp"] = erp if erp is not None else probe_snapshot.get("erp")
                    probe_snapshot["technologies"] = dict(tech)
                    probe_snapshot.setdefault("impact_distribution", {})
                    _merge_counts(current_snapshot["sensor_technologies"], tech)
                    current_probe = probe
                    in_global_summary = False
                    continue

                p2 = SENSORS_ON_PROBEID_RE.search(line)
                if p2:
                    probe_id = int(p2.group(1))
                    probe_name = p2.group(2).strip()
                    total = int(p2.group(3))
                    probe = probes_by_id.get(probe_id)
                    if probe is None:
                        probe = ProbeInfo(probe_id=probe_id, name=probe_name, sensor_count=total)
                        probes_by_id[probe_id] = probe
                    else:
                        probe.name = probe_name or probe.name
                        probe.sensor_count = total or probe.sensor_count
                    if not segment_probe_summary_reset:
                        current_snapshot["probes"] = []
                        current_snapshot["sensor_technologies"] = {}
                        segment_probe_summary_reset = True
                    probe_snapshot = _get_or_create_probe_snapshot(current_snapshot, probe_id, probe_name)
                    probe_snapshot["sensor_count"] = total
                    probe_snapshot.setdefault("impact_distribution", {})
                    current_probe = probe
                    in_global_summary = False
                    continue

                smry = SUMMARY_START_RE.search(line)
                if smry:
                    current_probe = None
                    in_global_summary = True

            if "splitted CPU settings" in line:
                scm = SPLITTED_CPU_RE.search(line)
                if scm:
                    assigned = int(scm.group(1))
                    total = int(scm.group(2))
                    res.cpu_assigned = assigned
                    res.cpu_total_for_splitting = total
                    res.cpu_splitting_active = assigned < total
                    current_snapshot["cpu_assigned"] = assigned
                    current_snapshot["cpu_total_for_splitting"] = total
                    current_snapshot["cpu_splitting_active"] = res.cpu_splitting_active

            if "Processmask:" in line:
                pmask = PROCESSMASK_RE.search(line)
                if pmask:
                    res.process_mask = pmask.group(1).strip()
                    current_snapshot["process_mask"] = res.process_mask

            if "Systemmask:" in line:
                smask = SYSTEMMASK_RE.search(line)
                if smask:
                    res.system_mask = smask.group(1).strip()
                    current_snapshot["system_mask"] = res.system_mask

            if "SystemID" in msg:
                sidm = SYSTEMID_RE.search(msg)
                if sidm:
                    res.system_id = sidm.group(1).strip()
                    current_snapshot["system_id"] = res.system_id
            if not res.system_id and "SYSTEMID-" in msg:
                aidm = ACTIVATION_SYSTEMID_RE.search(msg)
                if aidm:
                    res.system_id = aidm.group(1).strip()
                    current_snapshot["system_id"] = res.system_id

            if "CPU speed" in line:
                csm = CPU_SPEED_RE.search(line)
                if csm:
                    res.cpu_speed_ghz = float(csm.group(1))
                    current_snapshot["cpu_speed_ghz"] = res.cpu_speed_ghz

            if "Free Physical:" in line and "Total Physical:" in line:
                mm = MEM_RE.search(line)
                if mm:
                    res.free_ram_mb = _parse_int(mm.group(1))
                    res.total_ram_mb = _parse_int(mm.group(2))
                    res.free_pagefile_mb = _parse_int(mm.group(3))
                    res.total_pagefile_mb = _parse_int(mm.group(4))
                    current_snapshot["free_ram_mb"] = res.free_ram_mb
                    current_snapshot["total_ram_mb"] = res.total_ram_mb
                    current_snapshot["free_pagefile_mb"] = res.free_pagefile_mb
                    current_snapshot["total_pagefile_mb"] = res.total_pagefile_mb

            if "Memory manager:" in line:
                mmgr = MM_RE.search(line)
                if mmgr:
                    res.memory_manager = mmgr.group(1)
                    current_snapshot["memory_manager"] = res.memory_manager

            if "System time zone:" in line:
                tzm = TZ_RE.search(line)
                if tzm:
                    res.timezone = tzm.group(1).strip()
                    current_snapshot["timezone"] = res.timezone

            if "Installed:" in line and "Created:" in line and "License:" in line:
                idm = INSTALL_DATES_RE.search(line)
                if idm:
                    res.installed_date = idm.group(1)
                    res.created_date = idm.group(2)
                    res.license_date = idm.group(3)
                    current_snapshot["installed_date"] = res.installed_date
                    current_snapshot["created_date"] = res.created_date
                    current_snapshot["license_date"] = res.license_date

            if "Objects:" in line:
                objm = OBJECTS_RE.search(line)
                if objm:
                    for n, label in OBJECT_ITEM_RE.findall(objm.group(1)):
                        key = label.strip().lower()
                        val = int(n)
                        if key.startswith("probe"):
                            res.total_probes = val
                            current_snapshot["total_probes"] = val
                        elif key.startswith("sensor"):
                            res.total_sensors = val
                            current_snapshot["total_sensors"] = val
                        elif key.startswith("device"):
                            res.total_devices = val
                            current_snapshot["total_devices"] = val
                        elif key.startswith("group"):
                            res.total_groups = val
                            current_snapshot["total_groups"] = val
                        elif key.startswith("channel"):
                            res.total_channels = val
                            current_snapshot["total_channels"] = val
                        elif key.startswith("user(") or key.startswith("user(s)"):
                            res.total_users = val
                            current_snapshot["total_users"] = val

            if "impact on system performance" in line:
                im = IMPACT_RE.search(line)
                if im:
                    impact = _normalize_impact_label(im.group(1).strip())
                    total = int(im.group(2))
                    tech = _parse_tech_breakdown(im.group(3) or "")
                    lvl = ImpactLevel(total=total, sensors=tech)
                    if in_global_summary or current_probe is None:
                        res.global_impact_distribution[impact] = lvl
                        if not segment_global_impact_reset:
                            current_snapshot["global_impact_distribution"] = {}
                            segment_global_impact_reset = True
                        current_snapshot["global_impact_distribution"][impact] = {"total": total, "sensors": dict(tech)}
                    else:
                        current_probe.impact_distribution[impact] = lvl
                        probe_snapshot = _get_or_create_probe_snapshot(current_snapshot, current_probe.probe_id, current_probe.name)
                        if current_probe.probe_id not in segment_probe_impact_reset:
                            probe_snapshot["impact_distribution"] = {}
                            segment_probe_impact_reset.add(current_probe.probe_id)
                        probe_snapshot["impact_distribution"][impact] = {"total": total, "sensors": dict(tech)}
                    continue

            if "Sensors with Interval of" in line:
                iv = INTERVAL_RE.search(line)
                if iv:
                    interval_sec = int(iv.group(1))
                    total = int(iv.group(2))
                    tech = _parse_tech_breakdown(iv.group(3) or "")
                    res.interval_distribution[interval_sec] = IntervalInfo(total=total, sensors=tech)
                    if not segment_interval_reset:
                        current_snapshot["interval_distribution"] = {}
                        segment_interval_reset = True
                    current_snapshot["interval_distribution"][interval_sec] = {"total": total, "sensors": dict(tech)}
                    continue

            if "Estimated overall monitoring requests per second:" in line:
                erp_m = EST_RPS_RE.search(line)
                if erp_m:
                    try:
                        res.estimated_requests_per_second = float(erp_m.group(1))
                        res.total_erp = res.estimated_requests_per_second
                        current_snapshot["estimated_requests_per_second"] = res.estimated_requests_per_second
                        current_snapshot["total_erp"] = res.total_erp
                    except ValueError:
                        pass

            if "Sensors that exceed 50 channels:" in line:
                sc = SENSORS_50_CH_RE.search(line)
                if sc:
                    try:
                        res.sensors_exceeding_50_channels = int(sc.group(1))
                        current_snapshot["sensors_exceeding_50_channels"] = res.sensors_exceeding_50_channels
                    except ValueError:
                        pass

            if " sec " in line and "#" in line:
                for tm in THREAD_RE.finditer(line):
                    runtime = float(tm.group(2))
                    stat = ThreadStat(name=tm.group(1).strip(), runtime_sec=runtime, state=tm.group(3))
                    res.thread_stats.append(stat)
                    if runtime > res.max_thread_runtime:
                        res.max_thread_runtime = runtime
                    if not segment_thread_reset:
                        current_snapshot["thread_stats"] = []
                        current_snapshot["max_thread_runtime"] = 0.0
                        current_snapshot["long_running_threads"] = []
                        segment_thread_reset = True
                    stat_dict = {"name": stat.name, "runtime_sec": stat.runtime_sec, "state": stat.state}
                    current_snapshot["thread_stats"].append(stat_dict)
                    if runtime > float(current_snapshot.get("max_thread_runtime") or 0.0):
                        current_snapshot["max_thread_runtime"] = runtime

            if level in ("WARN", "ERRR") and ts_str:
                if _is_ignorable_license_message(msg):
                    continue

                if level == "WARN":
                    warn_count += 1
                    warning_occurrences.append(_WarningOccurrence(ts_str=ts_str))
                else:
                    err_count += 1
                    norm = _normalize_error_text(msg)
                    agg = patterns.get(norm)
                    if agg is None:
                        agg = _PatternAgg(count=0, first_seen=ts_str, last_seen=ts_str)
                        patterns[norm] = agg
                    agg.count += 1
                    agg.last_seen = ts_str
                    if len(agg.sample_lines) < 5:
                        agg.sample_lines.append(line)
                    error_occurrences.append(_ErrorOccurrence(ts_str=ts_str, ts=ts, pattern=norm, sample_line=line))
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    if current_snapshot is not None:
        _finalize_snapshot(current_snapshot)
        segment_snapshots_forward.append(current_snapshot)

    res.probes = sorted(probes_by_id.values(), key=lambda p: p.sensor_count, reverse=True)
    res.total_warnings = warn_count
    res.total_errors = err_count

    if first_ts and last_ts:
        res.log_span_days = (last_ts - first_ts).total_seconds() / 86400.0

    res.long_running_threads = [t for t in res.thread_stats if t.runtime_sec > 120.0]

    pat_list: List[ErrorPattern] = []
    for pat, agg in patterns.items():
        sev = "warning" if agg.count < 50 else "critical"
        pat_list.append(
            ErrorPattern(
                pattern=pat,
                count=agg.count,
                first_seen=agg.first_seen,
                last_seen=agg.last_seen,
                severity=sev,
            )
        )

    pat_list.sort(key=lambda p: p.count, reverse=True)
    res.error_patterns = pat_list[:500]
    res.top_errors = [
        ErrorDetail(
            rank=index,
            pattern=pattern.pattern,
            count=pattern.count,
            first_seen=pattern.first_seen,
            last_seen=pattern.last_seen,
            sample_lines=patterns[pattern.pattern].sample_lines[:5],
            severity=pattern.severity,
            explanation="",
        )
        for index, pattern in enumerate(pat_list[:10], start=1)
    ]

    restarts = sorted(res.restart_events, key=lambda r: r.timestamp)
    restart_ts = [restart.timestamp for restart in restarts]
    n_restarts = len(restarts)
    n_segments = n_restarts + 1
    patterns_per_segment: List[Dict[str, _PatternAgg]] = [{} for _ in range(n_segments)]
    error_timestamps_by_segment: List[List[str]] = [[] for _ in range(n_segments)]
    errors_per_segment = [0] * n_segments
    warnings_per_segment = [0] * n_segments

    def _segment_for_ts(ts_value: str) -> int:
        if not restart_ts:
            return 0
        return n_restarts - bisect_right(restart_ts, ts_value)

    for occurrence in error_occurrences:
        seg = _segment_for_ts(occurrence.ts_str)
        errors_per_segment[seg] += 1
        error_timestamps_by_segment[seg].append(occurrence.ts_str)
        agg = patterns_per_segment[seg].get(occurrence.pattern)
        if agg is None:
            agg = _PatternAgg(count=0, first_seen=occurrence.ts_str, last_seen=occurrence.ts_str)
            patterns_per_segment[seg][occurrence.pattern] = agg
        agg.count += 1
        agg.last_seen = occurrence.ts_str
        if len(agg.sample_lines) < 5:
            agg.sample_lines.append(occurrence.sample_line)

    for occurrence in warning_occurrences:
        seg = _segment_for_ts(occurrence.ts_str)
        warnings_per_segment[seg] += 1

    res.errors_since_last_restart = errors_per_segment[0] if n_restarts > 0 else 0

    end_ts = max_ts if max_ts is not None else last_ts
    if end_ts is not None:
        cutoff_24h = end_ts - timedelta(hours=24)
        res.errors_last_24h = sum(
            1 for occurrence in error_occurrences if occurrence.ts is not None and occurrence.ts >= cutoff_24h
        )

    res.error_patterns_by_segment = []
    for seg_idx in range(n_segments):
        seg_list: List[Dict[str, object]] = []
        for pat, agg in sorted(patterns_per_segment[seg_idx].items(), key=lambda item: item[1].count, reverse=True)[:100]:
            seg_list.append(
                {
                    "pattern": pat,
                    "count": agg.count,
                    "first_seen": agg.first_seen,
                    "last_seen": agg.last_seen,
                    "sample_lines": agg.sample_lines[:5],
                }
            )
        res.error_patterns_by_segment.append(seg_list)

    reversed_snapshots = list(reversed(segment_snapshots_forward))
    if len(reversed_snapshots) < n_segments:
        filler = _snapshot_from_result(res)
        while len(reversed_snapshots) < n_segments:
            reversed_snapshots.append(_copy_snapshot(filler))
    res.segment_snapshots = reversed_snapshots[:n_segments]
    res.errors_per_segment = errors_per_segment
    res.error_timestamps_by_segment = error_timestamps_by_segment
    res.warnings_per_segment = warnings_per_segment
    res.startup_milestones = milestones
    return res

