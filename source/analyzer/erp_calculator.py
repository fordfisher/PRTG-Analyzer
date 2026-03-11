from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import CoreLogResult


@dataclass(frozen=True)
class RefreshRateBucket:
    interval_sec: int
    interval_label: str
    count: int


def humanize_interval(interval_sec: int) -> str:
    if interval_sec < 60:
        return f"{interval_sec} sec"
    if interval_sec < 3600:
        m = interval_sec // 60
        return f"{m} min"
    if interval_sec < 86400:
        h = interval_sec // 3600
        return f"{h} hour" if h == 1 else f"{h} hours"
    d = interval_sec // 86400
    return f"{d} day" if d == 1 else f"{d} days"


def refresh_rate_distribution(core: CoreLogResult) -> List[RefreshRateBucket]:
    buckets: List[RefreshRateBucket] = []
    for interval_sec, info in sorted(core.interval_distribution.items(), key=lambda kv: kv[0]):
        buckets.append(
            RefreshRateBucket(
                interval_sec=interval_sec,
                interval_label=humanize_interval(interval_sec),
                count=info.total,
            )
        )
    return buckets


def calculate_total_requests_per_min(core: CoreLogResult) -> float:
    total = 0.0
    for interval_sec, info in core.interval_distribution.items():
        if interval_sec <= 0:
            continue
        total += (info.total * 60.0) / float(interval_sec)
    return total


def calculated_requests_per_min_by_interval(core: CoreLogResult) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for interval_sec, info in core.interval_distribution.items():
        if interval_sec <= 0:
            continue
        out[interval_sec] = (info.total * 60.0) / float(interval_sec)
    return out

