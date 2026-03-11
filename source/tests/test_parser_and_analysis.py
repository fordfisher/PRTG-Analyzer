from __future__ import annotations

import gzip
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from analyzer.analysis import apply_timeframe, run_analysis
from analyzer.core_log_parser import parse_core_log
from analyzer.erp_calculator import humanize_interval
from analyzer.models import CoreLogResult
from analyzer.report_generator import build_enterprise_html_report
from analyzer.rules_engine import evaluate
from analyzer.version import ANALYZER_VERSION


def _write_temp_log(text: str, *, suffix: str = ".log", encoding: str = "utf-8") -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding=encoding) as f:
        f.write(text.strip())
        return Path(f.name)


def _write_temp_gz_log(text: str, *, encoding: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".log.gz", delete=False) as tmp:
        path = Path(tmp.name)
    with gzip.open(path, "wt", encoding=encoding) as f:
        f.write(text.strip())
    return path


_SAMPLE_ANALYSIS_LOG = """
2026-03-01 08:00:00.000000 INFO TId 1000 Core> InitBasics: Logger initialized.
2026-03-01 08:00:01.000000 INFO TId 1000 Core> PRTG Network Monitor 26.1.1 core server starting on "prd-prtg-01"
2026-03-01 08:00:02.000000 INFO TId 1000 Core> Startup: OS: Microsoft Windows Server 2019 Datacenter, 12 CPUs (Intel Xeon), code page "Windows-1252", on "NVMe01"
2026-03-01 08:00:03.000000 INFO TId 1000 Core> Startup: Data path: D:\\PRTGData
2026-03-01 08:00:04.000000 INFO TId 1000 Core> Startup: System path: C:\\PRTGSystem
2026-03-01 08:00:05.000000 INFO TId 1000 Core> Paessler PRTG Enterprise Monitor licensed for "Example Corp" (001001-B5CQJS-RU2VDR-JNS2UK-N5WR7P-H4ZTGN-TCGFRT-KOIN24-DTN47D-5BMZK3) Edt=91,MaxS=5000
2026-03-01 08:00:06.000000 INFO TId 1000 Core> SystemID: SYSTEMID-AAAA-BBBB-CCCC
2026-03-01 08:00:07.000000 INFO TId 1000 Core> Current max. CPU speed 3.20 GHz
2026-03-01 08:00:08.000000 INFO TId 1000 Core> Free Physical: 16,384 MB Total Physical: 32,768 MB Free Pagefile: 20,000 MB Total Pagefile: 40,000 MB
2026-03-01 08:00:09.000000 INFO TId 1000 Core> Memory manager: jemalloc
2026-03-01 08:00:10.000000 INFO TId 1000 Core> System time zone: UTC
2026-03-01 08:00:11.000000 INFO TId 1000 Core> Installed: 2025-01-01 00:00:00 Created: 2025-01-02 00:00:00 License: 2025-01-03 00:00:00
2026-03-01 08:00:12.000000 INFO TId 1000 Core> Objects: 2x Probes, 120x Sensors, 15x Devices, 5x Groups, 90x Channels, 2x User(s)
2026-03-01 08:00:13.000000 INFO TId 1000 Core> Startup: Sensors on Probe ID 1 Local Probe (70 Sensors total - erps: 2.5) 30x ping 40x snmp
2026-03-01 08:00:14.000000 INFO TId 1000 Core> Startup: Sensors on Probe ID 2 Remote Probe (50 Sensors total - erps: 3.5) 20x http 30x wmi
2026-03-01 08:00:15.000000 INFO TId 1000 Core> Startup: Sensors for "summary" (120 Sensors total)
2026-03-01 08:00:16.000000 INFO TId 1000 Core> Sensors (Medium impact on system performance - 36 Sensors total): 20x ping 16x http
2026-03-01 08:00:17.000000 INFO TId 1000 Core> Sensors (High impact on system performance - 12 Sensors total): 12x snmp
2026-03-01 08:00:18.000000 INFO TId 1000 Core> Sensors with Interval of 30 Seconds (20 Sensors total): 20x ping
2026-03-01 08:00:19.000000 INFO TId 1000 Core> Sensors with Interval of 60 Seconds (100 Sensors total): 40x snmp 30x http 30x wmi
2026-03-01 08:00:20.000000 INFO TId 1000 Core> Estimated overall monitoring requests per second: 12.5
2026-03-01 08:00:21.000000 INFO TId 1000 Core> Sensors that exceed 50 channels: (12 total)
2026-03-01 08:00:22.000000 INFO TId 1000 Core> ProbeThread #1 180 sec Running
2026-03-01 09:00:00.000000 ERRR TId 1000 Core> Exception in SensorFactory: Timeout while reading sensor 12345
2026-03-01 09:00:05.000000 WARN TId 1000 Core> Warning before restart
2026-03-02 08:30:00.000000 INFO TId 1000 Core> InitBasics: Logger initialized.
2026-03-02 08:30:05.000000 ERRR TId 1000 Core> Exception in SensorFactory: Timeout while reading sensor 99999
2026-03-02 08:30:06.000000 ERRR TId 1000 Core> Probe disconnected on node 42
2026-03-02 08:30:07.000000 WARN TId 1000 Core> Warning after restart
2026-03-02 09:00:00.000000 INFO TId 1000 Core> End of log
"""


def test_parse_core_log_smoke() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        core = parse_core_log(path)
        assert core.server_name == "prd-prtg-01"
        assert core.prtg_version == "26.1.1"
        assert core.total_errors == 3
        assert core.total_warnings == 2
        assert core.first_timestamp != ""
        assert core.last_timestamp != ""
        assert core.log_span_days >= 0
        assert len(core.probes) == 2
        assert core.errors_last_24h == 3
        assert core.errors_since_last_restart == 2
        assert core.warnings_per_segment == [1, 1, 0]
    finally:
        path.unlink(missing_ok=True)


def test_analysis_smoke() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        assert "core" in result
        assert "score" in result
        assert 0 <= int(result["score"]) <= 100
        assert "findings" in result
        assert "refresh_rate_distribution" in result
        assert isinstance(result["refresh_rate_distribution"], list)

        core = result["core"]
        assert core["total_probes"] == 2
        assert core["total_sensors"] == 120
        assert core["errors_last_24h"] == 3
        assert core["errors_since_last_restart"] == 2
        assert len(core["error_patterns_by_segment"]) == 3
        assert isinstance(result["timeline"], list)
        assert result["metadata"]["analyzer_version"] == ANALYZER_VERSION
    finally:
        path.unlink(missing_ok=True)


def test_slider_data_contract() -> None:
    """The analysis result must provide all fields the frontend slider needs."""
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        core = result["core"]

        assert core["first_timestamp"], "first_timestamp must be non-empty"
        assert core["last_timestamp"], "last_timestamp must be non-empty"
        assert core["first_timestamp"] <= core["last_timestamp"]

        restarts = core["restart_events"]
        assert isinstance(restarts, list)
        assert len(restarts) >= 1
        for r in restarts:
            assert "timestamp" in r and r["timestamp"], "each restart needs a timestamp"

        timestamps = [r["timestamp"] for r in restarts]
        assert timestamps == sorted(timestamps), "restart_events must be sorted by timestamp"

        timeline = result["timeline"]
        assert isinstance(timeline, list) and len(timeline) >= 1
        for point in timeline:
            assert "timestamp" in point and "kind" in point and "label" in point
        tl_timestamps = [p["timestamp"] for p in timeline]
        assert tl_timestamps == sorted(tl_timestamps), "timeline must be sorted by timestamp"
    finally:
        path.unlink(missing_ok=True)


def test_humanize_interval() -> None:
    assert humanize_interval(30) == "30 sec"
    assert humanize_interval(60) == "1 min"
    assert humanize_interval(300) == "5 min"
    assert humanize_interval(3600) == "1 hour"
    assert humanize_interval(86400) == "1 day"


def test_report_generation_smoke() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        html = build_enterprise_html_report(result)
        assert "<!DOCTYPE html>" in html
        assert "PyPRTG_CLA Enterprise Report" in html
        assert "Example Corp" in html
    finally:
        path.unlink(missing_ok=True)


# Minimal log lines for CPU splitting, SystemID, and license owner parsing
_SAMPLE_CPU_LICENSE_LOG = """
2026-02-24 11:23:32.145324 INFO TId    7824 Core> InitBasics: Logger initialized.
2026-02-24 11:23:34.532294 INFO TId    7824 Core> Startup: OS: Microsoft Windows Server 2019 Datacenter (10.0 Build 17763), 18 CPUs (18x x64 Model 85 Step 0), code page "Windows-1252", on VMware
2026-02-24 11:23:34.532294 INFO TId    7824 Core> Running PRTG core server on splitted CPU settings (9/18)
2026-02-24 11:23:34.532294 INFO TId    7824 Core> Processmask: 0000000000000000000000000000000000000000000000111111111000000000
2026-02-24 11:23:34.532294 INFO TId    7824 Core> Systemmask:  0000000000000000000000000000000000000000000000111111111111111111
2026-02-24 11:23:34.976294 INFO TId    1372 Core> Paessler PRTG Enterprise Monitor licensed for "LGC Limited" (001001-B5CQJS-RU2VDR-JNS2UK-N5WR7P-H4ZTGN-TCGFRT-KOIN24-DTN47D-5BMZK3) Edt=91,MaxS=0
2026-02-24 11:23:34.976294 INFO TId    1372 Core> SystemID: SYSTEMID-FI7YFICX-MF24JJZD-SDVY4N7Y-UHAVZJ7T-U66IZ3IA
"""


def test_parse_cpu_splitting_and_license() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(_SAMPLE_CPU_LICENSE_LOG)
        path = Path(f.name)
    try:
        core = parse_core_log(path)
        assert core.cpu_splitting_active is True
        assert core.cpu_assigned == 9
        assert core.cpu_total_for_splitting == 18
        assert core.license_owner == "LGC Limited"
        assert "SYSTEMID-FI7YFICX" in core.system_id
        assert "0111111111000000000" in core.process_mask or "111111111" in core.process_mask
        assert "0111111111111111111" in core.system_mask or "111111111" in core.system_mask
    finally:
        path.unlink(missing_ok=True)


def test_cpu_splitting_rule_and_report_content() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(_SAMPLE_CPU_LICENSE_LOG)
        path = Path(f.name)
    try:
        result = run_analysis(str(path))
        core = result["core"]
        assert core.get("license_owner") == "LGC Limited"
        assert core.get("system_id", "").startswith("SYSTEMID-")
        assert core.get("cpu_splitting_active") is True
        assert core.get("cpu_assigned") == 9
        assert core.get("cpu_total_for_splitting") == 18

        analysis = evaluate(parse_core_log(path))
        rule_18 = [fr for fr in analysis.findings if fr.rule_id == "RULE_18_CPU_SPLITTING"]
        assert len(rule_18) == 1, "Expected one RULE_18_CPU_SPLITTING finding when splitting active and >8 CPUs"
        assert "same physical socket" in rule_18[0].recommendation

        html = build_enterprise_html_report(result)
        assert "LGC Limited" in html
        assert "License owner" in html
        assert "CPU splitting" in html
        assert "Active (9/18)" in html or "9" in html
    finally:
        path.unlink(missing_ok=True)


# Log with restarts and ERRR lines: segment 0 = after last "Logger initialized"
_SAMPLE_RESTART_ERRORS_LOG = """
2026-03-01 10:00:00.000000 INFO TId 1234 Core> InitBasics: Logger initialized.
2026-03-01 10:00:01.000000 ERRR TId 1234 Core> Error before second restart
2026-03-01 12:00:00.000000 INFO TId 1234 Core> InitBasics: Logger initialized.
2026-03-01 12:00:01.000000 ERRR TId 1234 Core> Error A after last restart
2026-03-01 12:00:02.000000 ERRR TId 1234 Core> Error B after last restart
"""


_SAMPLE_TIMEFRAME_SNAPSHOTS_LOG = """
2026-03-01 08:00:00.000000 INFO TId 1000 Core> InitBasics: Logger initialized.
2026-03-01 08:00:01.000000 INFO TId 1000 Core> PRTG Network Monitor 25.1.0 core server starting on "old-prtg-01"
2026-03-01 08:00:02.000000 INFO TId 1000 Core> Startup: OS: Microsoft Windows Server 2019 Datacenter, 8 CPUs (Intel Xeon Gold), code page "Windows-1252", on "SSD-OLD"
2026-03-01 08:00:03.000000 INFO TId 1000 Core> Startup: Data path: D:\\OldData
2026-03-01 08:00:04.000000 INFO TId 1000 Core> Startup: System path: C:\\OldSystem
2026-03-01 08:00:05.000000 INFO TId 1000 Core> Paessler PRTG Enterprise Monitor licensed for "Old Corp" (001001-B5CQJS-RU2VDR-JNS2UK-N5WR7P-H4ZTGN-TCGFRT-KOIN24-DTN47D-5BMZK3) Edt=91,MaxS=1000
2026-03-01 08:00:06.000000 INFO TId 1000 Core> SystemID: SYSTEMID-OLD-AAAA-BBBB
2026-03-01 08:00:07.000000 INFO TId 1000 Core> Current max. CPU speed 2.80 GHz
2026-03-01 08:00:08.000000 INFO TId 1000 Core> Free Physical: 8,192 MB Total Physical: 16,384 MB Free Pagefile: 10,000 MB Total Pagefile: 20,000 MB
2026-03-01 08:00:09.000000 INFO TId 1000 Core> Memory manager: jemalloc
2026-03-01 08:00:10.000000 INFO TId 1000 Core> System time zone: UTC
2026-03-01 08:00:11.000000 INFO TId 1000 Core> Objects: 1x Probes, 80x Sensors, 10x Devices, 3x Groups, 60x Channels, 1x User(s)
2026-03-01 08:00:12.000000 INFO TId 1000 Core> Startup: Sensors on Probe ID 1 Old Probe (80 Sensors total - erps: 2.0) 50x ping 30x http
2026-03-01 08:00:13.000000 INFO TId 1000 Core> Startup: Sensors for "summary" (80 Sensors total)
2026-03-01 08:00:14.000000 INFO TId 1000 Core> Sensors (Low impact on system performance - 50 Sensors total): 50x ping
2026-03-01 08:00:15.000000 INFO TId 1000 Core> Sensors (High impact on system performance - 30 Sensors total): 30x http
2026-03-01 08:00:16.000000 INFO TId 1000 Core> Sensors with Interval of 30 Seconds (20 Sensors total): 20x ping
2026-03-01 08:00:17.000000 INFO TId 1000 Core> Sensors with Interval of 60 Seconds (60 Sensors total): 30x ping 30x http
2026-03-01 08:00:18.000000 INFO TId 1000 Core> Estimated overall monitoring requests per second: 2.0
2026-03-01 08:00:19.000000 INFO TId 1000 Core> Sensors that exceed 50 channels: (3 total)
2026-03-01 08:00:20.000000 INFO TId 1000 Core> ProbeThread #1 90 sec Running
2026-03-01 08:30:00.000000 ERRR TId 1000 Core> Old version error
2026-03-02 09:00:00.000000 INFO TId 1000 Core> InitBasics: Logger initialized.
2026-03-02 09:00:01.000000 INFO TId 1000 Core> PRTG Network Monitor 26.2.0 core server starting on "new-prtg-01"
2026-03-02 09:00:02.000000 INFO TId 1000 Core> Startup: OS: Microsoft Windows Server 2022 Datacenter, 12 CPUs (Intel Xeon Platinum), code page "Windows-1252", on "SSD-NEW"
2026-03-02 09:00:03.000000 INFO TId 1000 Core> Startup: Data path: E:\\NewData
2026-03-02 09:00:04.000000 INFO TId 1000 Core> Startup: System path: C:\\NewSystem
2026-03-02 09:00:05.000000 INFO TId 1000 Core> Paessler PRTG Enterprise Monitor licensed for "New Corp" (001001-B5CQJS-RU2VDR-JNS2UK-N5WR7P-H4ZTGN-TCGFRT-KOIN24-DTN47D-5BMZK3) Edt=91,MaxS=5000
2026-03-02 09:00:06.000000 INFO TId 1000 Core> SystemID: SYSTEMID-NEW-CCCC-DDDD
2026-03-02 09:00:07.000000 INFO TId 1000 Core> Current max. CPU speed 3.60 GHz
2026-03-02 09:00:08.000000 INFO TId 1000 Core> Free Physical: 24,576 MB Total Physical: 65,536 MB Free Pagefile: 30,000 MB Total Pagefile: 60,000 MB
2026-03-02 09:00:09.000000 INFO TId 1000 Core> Memory manager: mimalloc
2026-03-02 09:00:10.000000 INFO TId 1000 Core> System time zone: CET
2026-03-02 09:00:11.000000 INFO TId 1000 Core> Running PRTG core server on splitted CPU settings (6/12)
2026-03-02 09:00:12.000000 INFO TId 1000 Core> Processmask: 000000111111
2026-03-02 09:00:13.000000 INFO TId 1000 Core> Systemmask:  111111111111
2026-03-02 09:00:14.000000 INFO TId 1000 Core> Objects: 2x Probes, 140x Sensors, 20x Devices, 5x Groups, 90x Channels, 2x User(s)
2026-03-02 09:00:15.000000 INFO TId 1000 Core> Startup: Sensors on Probe ID 1 Local Probe (90 Sensors total - erps: 4.5) 40x ping 50x snmp
2026-03-02 09:00:16.000000 INFO TId 1000 Core> Sensors (Medium impact on system performance - 30 Sensors total): 30x ping
2026-03-02 09:00:17.000000 INFO TId 1000 Core> Sensors (High impact on system performance - 60 Sensors total): 60x snmp
2026-03-02 09:00:18.000000 INFO TId 1000 Core> Startup: Sensors on Probe ID 2 Remote Probe (50 Sensors total - erps: 1.5) 20x http 30x wmi
2026-03-02 09:00:19.000000 INFO TId 1000 Core> Sensors (Low impact on system performance - 20 Sensors total): 20x http
2026-03-02 09:00:20.000000 INFO TId 1000 Core> Sensors (Medium impact on system performance - 30 Sensors total): 30x wmi
2026-03-02 09:00:21.000000 INFO TId 1000 Core> Startup: Sensors for "summary" (140 Sensors total)
2026-03-02 09:00:22.000000 INFO TId 1000 Core> Sensors (Medium impact on system performance - 70 Sensors total): 40x ping 30x wmi
2026-03-02 09:00:23.000000 INFO TId 1000 Core> Sensors (High impact on system performance - 60 Sensors total): 60x snmp
2026-03-02 09:00:24.000000 INFO TId 1000 Core> Sensors (Very High impact on system performance - 10 Sensors total): 10x http
2026-03-02 09:00:25.000000 INFO TId 1000 Core> Sensors with Interval of 30 Seconds (40 Sensors total): 40x ping
2026-03-02 09:00:26.000000 INFO TId 1000 Core> Sensors with Interval of 60 Seconds (100 Sensors total): 60x snmp 10x http 30x wmi
2026-03-02 09:00:27.000000 INFO TId 1000 Core> Estimated overall monitoring requests per second: 5.0
2026-03-02 09:00:28.000000 INFO TId 1000 Core> Sensors that exceed 50 channels: (12 total)
2026-03-02 09:00:29.000000 INFO TId 1000 Core> ProbeThread #2 240 sec Running
2026-03-02 09:30:00.000000 ERRR TId 1000 Core> New version error
2026-03-02 09:35:00.000000 WARN TId 1000 Core> New version warning
2026-03-02 10:00:00.000000 INFO TId 1000 Core> End of log
"""


def test_errors_since_last_restart() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(_SAMPLE_RESTART_ERRORS_LOG.strip())
        path = Path(f.name)
    try:
        core = parse_core_log(path)
        assert core.total_restarts == 2
        # Segment 0 = after last restart: only the two ERRR lines at 12:00:01 and 12:00:02
        assert core.errors_since_last_restart == 2
    finally:
        path.unlink(missing_ok=True)


def test_parse_core_log_stores_restart_segment_snapshots() -> None:
    path = _write_temp_log(_SAMPLE_TIMEFRAME_SNAPSHOTS_LOG)
    try:
        core = parse_core_log(path)
        assert len(core.segment_snapshots) == 3
        assert core.segment_snapshots[0]["prtg_version"] == "26.2.0"
        assert core.segment_snapshots[0]["total_sensors"] == 140
        assert core.segment_snapshots[0]["license_owner"] == "New Corp"
        assert len(core.segment_snapshots[0]["probes"]) == 2
        assert core.segment_snapshots[1]["prtg_version"] == "25.1.0"
        assert core.segment_snapshots[1]["total_sensors"] == 80
        assert core.segment_snapshots[1]["license_owner"] == "Old Corp"
        assert len(core.segment_snapshots[1]["probes"]) == 1
    finally:
        path.unlink(missing_ok=True)


# Log where last line sets last_ts; one ERRR within 24h of end, one outside
_SAMPLE_24H_ERRORS_LOG = """
2026-03-01 11:00:00.000000 ERRR TId 1 Core> Error 25h before end
2026-03-02 11:00:00.000000 ERRR TId 1 Core> Error 1h before end
2026-03-02 12:00:00.000000 INFO TId 1 Core> End of log
"""


def test_errors_last_24h() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(_SAMPLE_24H_ERRORS_LOG.strip())
        path = Path(f.name)
    try:
        core = parse_core_log(path)
        # last_timestamp = 2026-03-02 12:00; cutoff = 2026-03-01 12:00
        # Only the ERRR at 2026-03-02 11:00 is within 24h
        assert core.errors_last_24h == 1
    finally:
        path.unlink(missing_ok=True)


def test_errors_since_last_restart_zero_when_no_restarts() -> None:
    """When log has no 'Logger initialized', errors_since_last_restart is 0."""
    log_no_restart = """
2026-03-01 10:00:00.000000 ERRR TId 1 Core> Some error
2026-03-01 10:00:01.000000 ERRR TId 1 Core> Another error
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(log_no_restart.strip())
        path = Path(f.name)
    try:
        core = parse_core_log(path)
        assert core.total_restarts == 0
        assert core.errors_since_last_restart == 0
    finally:
        path.unlink(missing_ok=True)


def test_top_errors_use_errr_only_and_collapse_stackdump_ids() -> None:
    log_text = """
2026-03-10 03:09:44.249052 WARN TId 1968 Core> Warning that should not appear in Top Errors
2026-03-10 03:09:44.309559 ERRR TId 1968 Core> Exception in RawDataThread: File access denied(State=16) StackdumpId:{c57b2b76-6242-49b0-8680-82f7802c47f9}
2026-03-10 03:09:44.862272 ERRR TId 1968 Core> Exception in RawDataThread: File access denied(State=16) StackdumpId:{63bebc55-c372-4b30-81c3-d3a95c152aa0}
2026-03-10 03:09:45.142778 ERRR TId 1968 Core> Exception in RawDataThread: File access denied(State=16) StackdumpId:{17b29ec9-8bc9-4f1e-9a93-70dd30886080}
""".strip()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as f:
        f.write(log_text)
        path = Path(f.name)
    try:
        core = parse_core_log(path)
        assert core.total_warnings == 1
        assert core.total_errors == 3
        assert len(core.top_errors) == 1
        assert len(core.error_patterns) == 1
        assert len(core.error_patterns_by_segment) == 1
        assert len(core.error_patterns_by_segment[0]) == 1
        top = core.top_errors[0]
        assert top.count == 3
        assert "RawDataThread" in top.pattern
        assert "File access denied" in top.pattern
        assert "{<guid>}" in top.pattern
        assert all("ERRR" in line for line in top.sample_lines)
    finally:
        path.unlink(missing_ok=True)


def test_parse_core_log_gz_utf16_and_latin1() -> None:
    utf16_path = _write_temp_gz_log(_SAMPLE_ANALYSIS_LOG, encoding="utf-16")
    latin1_path = _write_temp_log(_SAMPLE_ANALYSIS_LOG, encoding="latin-1")
    try:
        utf16_core = parse_core_log(utf16_path)
        latin1_core = parse_core_log(latin1_path)
        assert utf16_core.total_errors == 3
        assert latin1_core.total_warnings == 2
    finally:
        utf16_path.unlink(missing_ok=True)
        latin1_path.unlink(missing_ok=True)


def test_parse_core_log_ignores_malformed_lines_without_crash() -> None:
    malformed = """
not-a-log-line
2026-03-02 10:00:00.000000 ERRR TId 1 Core> Valid error
broken ??? text
2026-03-02 10:00:01.000000 WARN TId 1 Core> Valid warning
"""
    path = _write_temp_log(malformed, encoding="utf-8", suffix=".txt")
    try:
        core = parse_core_log(path)
        assert core.total_errors == 1
        assert core.total_warnings == 1
    finally:
        path.unlink(missing_ok=True)


def test_apply_timeframe_invalid_values_return_original() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        assert apply_timeframe(result, None) is result
        assert apply_timeframe(result, "all") is result
        assert apply_timeframe(result, "invalid") is result
        assert apply_timeframe(result, "0") is result
    finally:
        path.unlink(missing_ok=True)


def test_apply_timeframe_recomputes_score_findings_and_top_errors() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        windowed = apply_timeframe(result, "1")
        assert windowed is not result
        assert windowed["core"]["total_errors"] == 2
        assert windowed["core"]["total_warnings"] == 1
        assert windowed["core"]["total_restarts"] == 1
        assert len(windowed["core"]["top_errors"]) == 2
        assert all(item["count"] == 1 for item in windowed["core"]["top_errors"])
        assert len(windowed["core"]["error_patterns"]) == 2
        assert isinstance(windowed["findings"], list)
    finally:
        path.unlink(missing_ok=True)


def test_apply_timeframe_updates_snapshot_fields_and_distributions() -> None:
    path = _write_temp_log(_SAMPLE_TIMEFRAME_SNAPSHOTS_LOG)
    try:
        result = run_analysis(str(path))
        latest = apply_timeframe(result, "1")
        previous = apply_timeframe(result, "2")

        assert latest["core"]["prtg_version"] == "26.2.0"
        assert latest["core"]["license_owner"] == "New Corp"
        assert latest["core"]["total_sensors"] == 140
        assert latest["core"]["total_probes"] == 2
        assert len(latest["core"]["probes"]) == 2
        assert latest["core"]["global_impact_distribution"]["Very High"]["total"] == 10
        assert latest["core"]["interval_distribution"][30]["total"] == 40
        assert latest["core"]["cpu_splitting_active"] is True
        assert latest["core"]["max_thread_runtime"] == 240
        assert latest["core"]["errors_since_last_restart"] == 1
        assert latest["calculated_requests_per_min"] == 180.0
        assert [bucket["count"] for bucket in latest["refresh_rate_distribution"]] == [40, 100]

        assert previous["core"]["prtg_version"] == "25.1.0"
        assert previous["core"]["license_owner"] == "Old Corp"
        assert previous["core"]["total_sensors"] == 80
        assert previous["core"]["total_probes"] == 1
        assert len(previous["core"]["probes"]) == 1
        assert previous["core"]["global_impact_distribution"]["Low"]["total"] == 50
        assert previous["core"]["global_impact_distribution"]["Medium"]["total"] == 70
        assert previous["core"]["global_impact_distribution"]["High"]["total"] == 90
        assert previous["core"]["global_impact_distribution"]["Very High"]["total"] == 10
        assert previous["core"]["interval_distribution"][30]["total"] == 60
        assert previous["core"]["interval_distribution"][60]["total"] == 160
        assert previous["core"]["cpu_splitting_active"] is False
        assert previous["core"]["max_thread_runtime"] == 90
        assert previous["core"]["errors_since_last_restart"] == 2
        assert previous["calculated_requests_per_min"] == 280.0
        assert [bucket["count"] for bucket in previous["refresh_rate_distribution"]] == [60, 160]
        assert previous["core"]["total_errors"] == 2
        assert previous["core"]["total_warnings"] == 1
        assert len(previous["findings"]) >= 1
    finally:
        path.unlink(missing_ok=True)


def test_apply_timeframe_aggregates_distributions_across_segments() -> None:
    """Distributions should be summed over all segments in the time window, not taken from a single snapshot."""
    path = _write_temp_log(_SAMPLE_TIMEFRAME_SNAPSHOTS_LOG)
    try:
        result = run_analysis(str(path))

        single = apply_timeframe(result, "1")
        combined = apply_timeframe(result, "2")

        seg0_impact = single["core"]["global_impact_distribution"]
        assert seg0_impact["Medium"]["total"] == 70
        assert seg0_impact["High"]["total"] == 60
        assert seg0_impact["Very High"]["total"] == 10

        comb_impact = combined["core"]["global_impact_distribution"]
        assert comb_impact["Low"]["total"] == 50
        assert comb_impact["Medium"]["total"] == 70
        assert comb_impact["High"]["total"] == 90
        assert comb_impact["Very High"]["total"] == 10
        assert comb_impact["High"]["sensors"]["snmp"] == 60
        assert comb_impact["High"]["sensors"]["http"] == 30

        seg0_interval = single["core"]["interval_distribution"]
        assert seg0_interval[30]["total"] == 40
        assert seg0_interval[60]["total"] == 100

        comb_interval = combined["core"]["interval_distribution"]
        assert comb_interval[30]["total"] == 60
        assert comb_interval[30]["sensors"]["ping"] == 60
        assert comb_interval[60]["total"] == 160
        assert comb_interval[60]["sensors"]["snmp"] == 60
        assert comb_interval[60]["sensors"]["http"] == 40
        assert comb_interval[60]["sensors"]["wmi"] == 30
        assert comb_interval[60]["sensors"]["ping"] == 30

        assert combined["calculated_requests_per_min"] > single["calculated_requests_per_min"]
    finally:
        path.unlink(missing_ok=True)


def test_report_masks_license_key_and_timeframe_top_errors() -> None:
    path = _write_temp_log(_SAMPLE_ANALYSIS_LOG)
    try:
        result = run_analysis(str(path))
        html = build_enterprise_html_report(result, errors_time_frame="1")
        assert "001001-B5CQJS-RU2VDR-JNS2UK-N5WR7P-H4ZTGN-TCGFRT-KOIN24-DTN47D-5BMZK3" not in html
        assert "Example Corp" in html
        assert "Top Errors (Past 1 restart)" in html
        assert "Probe disconnected on node &lt;n&gt;" in html
        assert "Timeout while reading sensor &lt;n&gt;" in html
    finally:
        path.unlink(missing_ok=True)


def test_parse_core_log_large_file_perf_budget() -> None:
    repeated = "\n".join(
        f"2026-03-01 10:{idx // 60:02d}:{idx % 60:02d}.000000 ERRR TId 1 Core> Burst error {idx}"
        for idx in range(5000)
    )
    path = _write_temp_log(
        "\n".join(
            [
                "2026-03-01 09:59:00.000000 INFO TId 1 Core> InitBasics: Logger initialized.",
                repeated,
                "2026-03-01 11:30:00.000000 INFO TId 1 Core> End of log",
            ]
        )
    )
    try:
        started = time.perf_counter()
        core = parse_core_log(path)
        elapsed = time.perf_counter() - started
        assert core.total_errors == 5000
        assert elapsed < 8.0
    finally:
        path.unlink(missing_ok=True)


def test_parse_core_log_segment_assignment_many_restarts_perf() -> None:
    lines = []
    for idx in range(200):
        lines.append(f"2026-03-01 {idx // 60:02d}:{idx % 60:02d}:00.000000 INFO TId 1 Core> InitBasics: Logger initialized.")
        lines.append(f"2026-03-01 {idx // 60:02d}:{idx % 60:02d}:01.000000 ERRR TId 1 Core> Restart error {idx}")
        lines.append(f"2026-03-01 {idx // 60:02d}:{idx % 60:02d}:02.000000 WARN TId 1 Core> Restart warning {idx}")
    path = _write_temp_log("\n".join(lines))
    try:
        started = time.perf_counter()
        core = parse_core_log(path)
        elapsed = time.perf_counter() - started
        assert core.total_restarts == 200
        assert sum(core.errors_per_segment) == 200
        assert sum(core.warnings_per_segment) == 200
        assert elapsed < 5.0
    finally:
        path.unlink(missing_ok=True)


def test_rules_engine_score_clamped_0_to_100() -> None:
    core = CoreLogResult(
        total_sensors=20000,
        cpu_count=1,
        total_ram_mb=1024,
        data_path="C:\\Data",
        system_path="C:\\System",
        os_version="Microsoft Windows Server 2012",
        total_errors=500,
        error_patterns=[{"pattern": "err", "count": 500, "first_seen": "a", "last_seen": "b", "severity": "critical"}],
        total_restarts=20,
        max_thread_runtime=600,
        global_impact_distribution={"High": {"total": 10000, "sensors": {}}},
        cpu_splitting_active=True,
        cpu_total_for_splitting=16,
        cpu_assigned=8,
        sensors_exceeding_50_channels=30,
        interval_distribution={30: {"total": 20000, "sensors": {"ping": 20000}}},
    )
    result = evaluate(core)
    assert 0 <= result.score <= 100


def test_api_analyze_progress_result_export_happy_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()
    client = TestClient(app_module.app)

    response = client.post(
        "/api/analyze",
        files={"core_log": ("core.log", _SAMPLE_ANALYSIS_LOG.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    file_hash = payload["hash"]

    progress = client.get(f"/api/progress/{job_id}")
    assert progress.status_code == 200
    assert '"status": "done"' in progress.text

    result = client.get(f"/api/result/{file_hash}?timeframe=1")
    assert result.status_code == 200
    assert result.json()["core"]["total_errors"] == 2

    export_json = client.get(f"/api/export/json/{file_hash}")
    assert export_json.status_code == 200
    export_html = client.get(f"/api/export/html/{file_hash}?timeframe=1")
    assert export_html.status_code == 200
    assert "Top Errors (Past 1 restart)" in export_html.text


def test_api_timeframe_returns_timeframed_snapshot_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()
    client = TestClient(app_module.app)

    response = client.post(
        "/api/analyze",
        files={"core_log": ("core.log", _SAMPLE_TIMEFRAME_SNAPSHOTS_LOG.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    file_hash = payload["hash"]

    progress = client.get(f"/api/progress/{job_id}")
    assert progress.status_code == 200
    assert '"status": "done"' in progress.text

    previous = client.get(f"/api/result/{file_hash}?timeframe=2")
    assert previous.status_code == 200
    body = previous.json()
    assert body["core"]["prtg_version"] == "25.1.0"
    assert body["core"]["license_owner"] == "Old Corp"
    assert body["core"]["total_sensors"] == 80
    assert body["calculated_requests_per_min"] == 280.0
    assert [bucket["count"] for bucket in body["refresh_rate_distribution"]] == [60, 160]

    export_html = client.get(f"/api/export/html/{file_hash}?timeframe=2")
    assert export_html.status_code == 200
    assert "25.1.0" in export_html.text
    assert "Old Corp" in export_html.text


def test_api_cache_version_mismatch_recompute(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()

    calls = {"count": 0}
    real_run_analysis = app_module.run_analysis

    def wrapped(path: str, **kwargs):
        calls["count"] += 1
        return real_run_analysis(path, **kwargs)

    monkeypatch.setattr(app_module, "run_analysis", wrapped)

    uploaded_bytes = _SAMPLE_ANALYSIS_LOG.encode("utf-8")
    file_hash = __import__("hashlib").sha256(uploaded_bytes).hexdigest()
    stale_path = tmp_path / f"{file_hash}.json"
    stale_path.write_text(
        '{"core": {}, "score": 1, "findings": [], "refresh_rate_distribution": [], "calculated_requests_per_min": 0, "timeline": [], "metadata": {"analyzer_version": "old"}}',
        encoding="utf-8",
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/analyze",
        files={"core_log": ("core.log", uploaded_bytes, "text/plain")},
    )
    assert response.status_code == 200
    assert calls["count"] == 1
    result = client.get(f"/api/result/{file_hash}")
    assert result.status_code == 200
    assert result.json()["metadata"]["analyzer_version"] == ANALYZER_VERSION


def test_api_missing_hash_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()
    client = TestClient(app_module.app)
    response = client.get("/api/result/does-not-exist")
    assert response.status_code == 404


_MINIMAL_STATUS_HTML_FOR_API = """
<html><body>
<div class="screenbox"><h2>Software Version and Server Information</h2>
<ul><li><span>Server CPU Load</span><span>7%</span></li></ul></div>
<div class="screenbox"><h2>Database Objects</h2>
<ul><li><span>Sensors</span><span>250</span></li><li><span>Probes</span><span>3</span></li>
<li><span>Requests/Second</span><span>20</span></li></ul></div>
<div class="screenbox"><h2>Sensors Sorted by Impact on System Performance</h2>
<ul><li><span>Very low</span><span>50x ping</span></li><li><span>Low</span><span>100x snmp</span></li>
<li><span>Medium</span><span>80x http</span></li><li><span>High</span><span></span></li>
<li><span>Very high</span><span></span></li></ul></div>
<div class="screenbox"><h2>Web Server Activity</h2>
<ul><li><span>Slow Request Ratio</span><span> 15%</span></li></ul></div>
</body></html>
"""


def test_api_analyze_with_status_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()
    client = TestClient(app_module.app)

    response = client.post(
        "/api/analyze",
        files={
            "core_log": ("core.log", _SAMPLE_ANALYSIS_LOG.encode("utf-8"), "text/plain"),
            "status_data": ("status.htm", _MINIMAL_STATUS_HTML_FOR_API.encode("utf-8"), "text/html"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    file_hash = payload["hash"]

    progress = client.get(f"/api/progress/{job_id}")
    assert progress.status_code == 200
    assert '"status": "done"' in progress.text

    result = client.get(f"/api/result/{file_hash}")
    assert result.status_code == 200
    body = result.json()
    assert "status_snapshot" in body
    snap = body["status_snapshot"]
    assert snap["server_cpu_load_pct"] == 7.0
    assert snap["total_sensors"] == 250
    assert snap["requests_per_second"] == 20
    assert snap["slow_request_ratio_pct"] == 15.0
    assert snap["impact_distribution"]["Very low"]["total"] == 50
    assert snap["impact_distribution"]["Low"]["total"] == 100
    assert snap["impact_distribution"]["Medium"]["total"] == 80


def test_api_analyze_without_status_data_has_no_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CACHE_DIR", tmp_path)
    app_module.JOBS.clear()
    app_module.RESULT_MEMO.clear()
    client = TestClient(app_module.app)

    response = client.post(
        "/api/analyze",
        files={"core_log": ("core.log", _SAMPLE_ANALYSIS_LOG.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    file_hash = payload["hash"]

    progress = client.get(f"/api/progress/{job_id}")
    assert progress.status_code == 200

    result = client.get(f"/api/result/{file_hash}")
    assert result.status_code == 200
    body = result.json()
    assert "status_snapshot" not in body

