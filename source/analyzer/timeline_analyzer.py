from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .models import CoreLogResult


@dataclass(frozen=True)
class TimelinePoint:
    timestamp: str
    kind: str  # "restart" | "milestone"
    label: str


def build_timeline(core: CoreLogResult) -> List[TimelinePoint]:
    points: List[TimelinePoint] = []
    for r in core.restart_events:
        if r.timestamp:
            points.append(TimelinePoint(timestamp=r.timestamp, kind="restart", label="Logger initialized"))
    for m in core.startup_milestones:
        if m.timestamp:
            points.append(TimelinePoint(timestamp=m.timestamp, kind="milestone", label=m.name))

    def _key(p: TimelinePoint) -> float:
        try:
            return datetime.fromisoformat(p.timestamp).timestamp()
        except Exception:
            return 0.0

    points.sort(key=_key)
    return points

