from __future__ import annotations

import re
from typing import List

from .erp_calculator import calculate_total_requests_per_min
from .models import AnalysisResult, CoreLogResult, EvidenceItem, Finding


def _recommended_cpu_cores(total_sensors: int) -> int:
    if total_sensors >= 10000:
        return 16
    if total_sensors >= 5000:
        return 12
    if total_sensors >= 2500:
        return 8
    return 4


def _recommended_ram_gb(total_sensors: int) -> int:
    if total_sensors >= 10000:
        return 64
    if total_sensors >= 5000:
        return 32
    if total_sensors >= 2500:
        return 16
    return 8


def _impact_totals(core: CoreLogResult) -> tuple[int, int, int]:
    medium = (core.global_impact_distribution.get("Medium").total if core.global_impact_distribution.get("Medium") else 0)
    high = (core.global_impact_distribution.get("High").total if core.global_impact_distribution.get("High") else 0)
    very_high = (core.global_impact_distribution.get("Very High").total if core.global_impact_distribution.get("Very High") else 0)
    return medium, high, very_high


def _tone(over_ratio: float) -> str:
    # over_ratio = actual/threshold - 1.0
    if over_ratio <= 0.10:
        return "Consider"
    if over_ratio <= 0.50:
        return "We recommend"
    return "Immediate action required"


def _add_finding(findings: List[Finding], *, rule_id: str, severity: str, score_delta: int, title: str, rec: str, evidence: List[EvidenceItem]) -> None:
    findings.append(
        Finding(
            rule_id=rule_id,
            severity=severity,
            score_delta=score_delta,
            title=title,
            recommendation=rec,
            evidence=evidence,
        )
    )


def evaluate(core: CoreLogResult) -> AnalysisResult:
    score = 100
    findings: List[Finding] = []

    # RULE 1: CPU cores vs sensor count
    sensors = core.total_sensors or 0
    cpu = core.cpu_count or 0
    required = _recommended_cpu_cores(sensors)
    if required > 0 and cpu > 0 and cpu < int(required * 0.95):
        score -= 10
        _add_finding(
            findings,
            rule_id="RULE_1_CPU",
            severity="red",
            score_delta=-10,
            title="CPU cores below recommended for sensor count",
            rec=f"{_tone((required/cpu)-1.0)} increasing CPU cores to at least {required} for {sensors} sensors.",
            evidence=[
                EvidenceItem(label="total_sensors", value=str(sensors)),
                EvidenceItem(label="cpu_count", value=str(cpu)),
                EvidenceItem(label="recommended_cpu_cores", value=str(required)),
            ],
        )

    # RULE 2: RAM sizing (tier-based shortcut + formula)
    ram_gb = (core.total_ram_mb or 0) / 1024.0
    min_tier_gb = _recommended_ram_gb(sensors)
    if ram_gb > 0 and ram_gb < min_tier_gb * 0.90:
        score -= 10
        _add_finding(
            findings,
            rule_id="RULE_2_RAM",
            severity="red",
            score_delta=-10,
            title="RAM below recommended tier",
            rec=f"{_tone((min_tier_gb/ram_gb)-1.0)} increasing RAM to at least {min_tier_gb} GB.",
            evidence=[
                EvidenceItem(label="total_ram_gb", value=f"{ram_gb:.1f}"),
                EvidenceItem(label="recommended_ram_gb", value=str(min_tier_gb)),
            ],
        )

    # RULE 3 + RULE 13: drive separation
    data_drive = (core.data_path[:2].upper() if core.data_path and len(core.data_path) >= 2 else "")
    sys_drive = (core.system_path[:2].upper() if core.system_path and len(core.system_path) >= 2 else "")
    if data_drive and sys_drive and data_drive == sys_drive:
        score -= 5
        _add_finding(
            findings,
            rule_id="RULE_13_DRIVES",
            severity="yellow",
            score_delta=-5,
            title="Data and System path on same drive",
            rec="We recommend placing the PRTG data directory on a dedicated fast SSD/NVMe volume separate from the system volume.",
            evidence=[EvidenceItem(label="data_path", value=core.data_path), EvidenceItem(label="system_path", value=core.system_path)],
        )

    # RULE 4: OS version
    os_text = core.os_version or ""
    year_match = re.search(r"\b(2008|2012|2016|2019|2022|2025)\b", os_text)
    if year_match:
        year = int(year_match.group(1))
        if year in (2008, 2012):
            score -= 10
            _add_finding(
                findings,
                rule_id="RULE_4_OS",
                severity="red",
                score_delta=-10,
                title="Deprecated Windows Server version",
                rec="Immediate action required: upgrade the OS to a supported Windows Server version (2019+; 2022/2025 recommended).",
                evidence=[EvidenceItem(label="os_version", value=os_text)],
            )
        elif year == 2016:
            score -= 5
            _add_finding(
                findings,
                rule_id="RULE_4_OS",
                severity="yellow",
                score_delta=-5,
                title="Aging Windows Server version",
                rec="We recommend upgrading to Windows Server 2022/2025 for best performance and supportability.",
                evidence=[EvidenceItem(label="os_version", value=os_text)],
            )

    # RULE 7: errors
    unique_patterns = len(core.error_patterns or [])
    if core.total_errors > 0:
        delta = -5 if unique_patterns <= 50 else -8
        score += delta
        sev = "yellow" if unique_patterns <= 50 else "red"
        _add_finding(
            findings,
            rule_id="RULE_7_ERRORS",
            severity=sev,
            score_delta=delta,
            title="Errors detected in Core.log (license/activation excluded)",
            rec="We recommend addressing the recurring error patterns in the Top 5 list first, then validating stability over time.",
            evidence=[
                EvidenceItem(label="total_errors", value=str(core.total_errors)),
                EvidenceItem(label="unique_error_patterns", value=str(unique_patterns)),
            ],
        )

    # RULE 14: restart frequency
    if core.total_restarts > 10:
        score -= 5
        _add_finding(
            findings,
            rule_id="RULE_14_RESTARTS",
            severity="red",
            score_delta=-5,
            title="High restart frequency detected",
            rec="Immediate action required: investigate why the core service restarts frequently (crashes, resource pressure, updates).",
            evidence=[EvidenceItem(label="total_restarts", value=str(core.total_restarts))],
        )
    elif core.total_restarts > 5:
        score -= 3
        _add_finding(
            findings,
            rule_id="RULE_14_RESTARTS",
            severity="yellow",
            score_delta=-3,
            title="Elevated restart frequency detected",
            rec="We recommend reviewing restart timestamps and correlating with Top 5 errors and resource constraints.",
            evidence=[EvidenceItem(label="total_restarts", value=str(core.total_restarts))],
        )

    # RULE 15: long-running threads
    if core.max_thread_runtime > 300:
        score -= 5
        _add_finding(
            findings,
            rule_id="RULE_15_THREADS",
            severity="red",
            score_delta=-5,
            title="Very long-running threads detected",
            rec="Immediate action required: identify blocked/slow threads and reduce load (intervals, heavy sensors, DB/IO bottlenecks).",
            evidence=[EvidenceItem(label="max_thread_runtime_sec", value=f"{core.max_thread_runtime:.2f}")],
        )
    elif core.max_thread_runtime > 120:
        score -= 3
        _add_finding(
            findings,
            rule_id="RULE_15_THREADS",
            severity="yellow",
            score_delta=-3,
            title="Long-running threads detected",
            rec="We recommend investigating thread runtime hotspots and validating disk/database performance and heavy sensors.",
            evidence=[EvidenceItem(label="max_thread_runtime_sec", value=f"{core.max_thread_runtime:.2f}")],
        )

    # RULE 16: impact distribution warning
    total = core.total_sensors or 0
    medium, high, vhigh = _impact_totals(core)
    if total > 0:
        ratio = (medium + high + vhigh) / float(total)
        if ratio > 0.30:
            score -= 4
            _add_finding(
                findings,
                rule_id="RULE_16_IMPACT",
                severity="yellow",
                score_delta=-4,
                title="Large share of medium/high impact sensors",
                rec="We recommend reducing load by increasing intervals for heavier sensors and reviewing sensor types with high impact.",
                evidence=[
                    EvidenceItem(label="total_sensors", value=str(total)),
                    EvidenceItem(label="medium_high_very_high_count", value=str(medium + high + vhigh)),
                    EvidenceItem(label="ratio", value=f"{ratio:.2%}"),
                ],
            )

    # RULE 18: CPU splitting — recommend disable when more than 8 CPUs and splitting active
    total_cpus = core.cpu_total_for_splitting or core.cpu_count or 0
    if core.cpu_splitting_active and total_cpus > 8:
        assigned = core.cpu_assigned or 0
        score -= 4
        _add_finding(
            findings,
            rule_id="RULE_18_CPU_SPLITTING",
            severity="yellow",
            score_delta=-4,
            title="CPU splitting active with more than 8 CPUs",
            rec="We recommend disabling CPU splitting when using more than 8 CPUs and ensuring all active cores are on the same physical socket for best performance.",
            evidence=[
                EvidenceItem(label="cpu_assigned", value=str(assigned)),
                EvidenceItem(label="cpu_total", value=str(total_cpus)),
            ],
        )

    # RULE 17: sensors exceeding 50 channels
    if core.sensors_exceeding_50_channels > 10:
        score -= 3
        _add_finding(
            findings,
            rule_id="RULE_17_CHANNELS",
            severity="yellow",
            score_delta=-3,
            title="Many sensors exceed 50 channels",
            rec="We recommend reducing channel count for affected sensors (optimize templates, split sensors, or disable unused channels).",
            evidence=[EvidenceItem(label="sensors_exceeding_50_channels", value=str(core.sensors_exceeding_50_channels))],
        )

    # RULE 11: overall load heuristic from interval distribution (global)
    total_rpm = calculate_total_requests_per_min(core)
    if total_rpm > 15000:
        score -= 10
        _add_finding(
            findings,
            rule_id="RULE_11_ERP",
            severity="red",
            score_delta=-10,
            title="High scanning load indicated by interval distribution",
            rec="Immediate action required: increase scanning intervals and reduce heavy sensor frequency to lower requests/minute.",
            evidence=[EvidenceItem(label="calculated_requests_per_min", value=f"{total_rpm:.0f}")],
        )
    elif total_rpm > 10000:
        score -= 6
        _add_finding(
            findings,
            rule_id="RULE_11_ERP",
            severity="yellow",
            score_delta=-6,
            title="Elevated scanning load indicated by interval distribution",
            rec="We recommend reviewing short intervals (30s/60s) and aligning intervals with best practices.",
            evidence=[EvidenceItem(label="calculated_requests_per_min", value=f"{total_rpm:.0f}")],
        )

    score = max(0, min(100, score))
    return AnalysisResult(score=score, findings=findings)

