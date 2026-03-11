from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ImpactLevel(BaseModel):
    total: int = 0
    sensors: Dict[str, int] = Field(default_factory=dict)


class IntervalInfo(BaseModel):
    total: int = 0
    sensors: Dict[str, int] = Field(default_factory=dict)


class ProbeInfo(BaseModel):
    probe_id: int
    name: str
    sensor_count: int = 0
    erp: Optional[float] = None
    technologies: Dict[str, int] = Field(default_factory=dict)
    impact_distribution: Dict[str, ImpactLevel] = Field(default_factory=dict)


class Milestone(BaseModel):
    name: str
    timestamp: str


class ThreadStat(BaseModel):
    name: str
    runtime_sec: float
    state: str


class RestartEvent(BaseModel):
    timestamp: str


class ErrorPattern(BaseModel):
    pattern: str
    count: int
    first_seen: str
    last_seen: str
    severity: str


class ErrorDetail(BaseModel):
    rank: int
    pattern: str
    count: int
    first_seen: str
    last_seen: str
    sample_lines: List[str] = Field(default_factory=list)
    severity: str
    explanation: str = ""


class EvidenceItem(BaseModel):
    label: str
    value: str


class Finding(BaseModel):
    rule_id: str
    severity: str  # "green" | "yellow" | "red" | "info"
    score_delta: int = 0
    title: str
    recommendation: str
    evidence: List[EvidenceItem] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    score: int
    findings: List[Finding]


class CoreLogResult(BaseModel):
    # === GLOBAL INFO ===
    server_name: str = ""
    prtg_version: str = ""
    license_owner: str = ""
    license_key: str = ""
    system_id: str = ""
    edition_type: str = ""
    commercial_days_left: Optional[int] = None
    max_sensors: int = 0
    os_version: str = ""
    cpu_count: int = 0
    cpu_model: str = ""
    cpu_speed_ghz: float = 0.0
    cpu_splitting_active: bool = False
    cpu_assigned: Optional[int] = None
    cpu_total_for_splitting: Optional[int] = None
    process_mask: str = ""
    system_mask: str = ""
    total_ram_mb: int = 0
    free_ram_mb: int = 0
    total_pagefile_mb: int = 0
    free_pagefile_mb: int = 0
    data_path: str = ""
    system_path: str = ""
    storage_device: str = ""
    timezone: str = ""
    memory_manager: str = ""
    installed_date: Optional[str] = None
    created_date: Optional[str] = None
    license_date: Optional[str] = None

    # === OBJECTS SUMMARY ===
    total_sensors: int = 0
    total_probes: int = 0
    total_devices: int = 0
    total_groups: int = 0
    total_channels: int = 0
    total_users: int = 0

    # === PROBES ===
    probes: List[ProbeInfo] = Field(default_factory=list)

    # === GLOBAL IMPACT DISTRIBUTION ===
    global_impact_distribution: Dict[str, ImpactLevel] = Field(default_factory=dict)

    # === SENSOR TECHNOLOGIES (global) ===
    sensor_technologies: Dict[str, int] = Field(default_factory=dict)

    # === INTERVAL DISTRIBUTION ===
    interval_distribution: Dict[int, IntervalInfo] = Field(default_factory=dict)

    # === STARTUP ===
    startup_duration_sec: Optional[float] = None
    xml_load_duration_sec: Optional[float] = None
    cache_load_duration_sec: Optional[float] = None
    datastate_init_duration_sec: Optional[float] = None
    startup_milestones: List[Milestone] = Field(default_factory=list)

    # === THREAD STATS ===
    thread_stats: List[ThreadStat] = Field(default_factory=list)
    max_thread_runtime: float = 0.0
    long_running_threads: List[ThreadStat] = Field(default_factory=list)

    # === TOP ERRORS ===
    top_errors: List[ErrorDetail] = Field(default_factory=list)

    # === ERRORS BY RESTART SEGMENT (for time-frame filter) ===
    # Segment 0 = from last restart to end, 1 = second-last to last, ... N = start to first restart.
    # Each segment: list of {"pattern", "count", "first_seen", "last_seen", "sample_lines"} for that segment.
    segment_snapshots: List[Dict[str, Any]] = Field(default_factory=list)
    error_patterns_by_segment: List[List[Dict[str, Any]]] = Field(default_factory=list)
    error_timestamps_by_segment: List[List[str]] = Field(default_factory=list)
    errors_per_segment: List[int] = Field(default_factory=list)
    warnings_per_segment: List[int] = Field(default_factory=list)

    # === ALL ERROR PATTERNS ===
    error_patterns: List[ErrorPattern] = Field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0
    errors_last_24h: int = 0
    errors_since_last_restart: int = 0

    # === TIMELINE ===
    restart_events: List[RestartEvent] = Field(default_factory=list)
    total_restarts: int = 0
    log_span_days: float = 0.0
    first_timestamp: str = ""
    last_timestamp: str = ""

    # === ERP ===
    total_erp: float = 0.0
    erp_per_probe: Dict[str, float] = Field(default_factory=dict)

    # === MISC ===
    sensors_exceeding_50_channels: int = 0
    estimated_requests_per_second: float = 0.0

