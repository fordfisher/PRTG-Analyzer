"""Parse PRTG Status Data files from support bundles.

Handles two formats found in support bundles:
1. **HTML** (``PRTG Status Data.htm``) – rich page with CPU load, impact
   distribution, requests/second, slow request ratio, etc.
2. **JSON** (``Status Data.htm``) – lightweight JSON blob with sensor
   status counts (up, warning, paused, unknown, down/alarm).
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_COUNT_RE = re.compile(r"(\d+)x\s+")
_IMPACT_LEVELS = ("Very low", "Low", "Medium", "High", "Very high")
_IMPACT_LOWER = {k.lower(): k for k in _IMPACT_LEVELS}

# Known localized labels for impact levels (currently German),
# mapped back to the canonical English keys in ``_IMPACT_LEVELS``.
_IMPACT_ALIASES = {
    "sehr niedrig": "Very low",
    "niedrig": "Low",
    "mittel": "Medium",
    "hoch": "High",
    "sehr hoch": "Very high",
}


class _SectionExtractor(HTMLParser):
    """Single-pass HTML parser that collects key-value pairs grouped by <h2> section."""

    def __init__(self) -> None:
        super().__init__()
        self._current_section: str = ""
        self._in_span = False
        self._span_texts: List[str] = []
        self._current_text = ""
        self._pairs: Dict[str, List[Tuple[str, str]]] = {}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "h2":
            self._current_text = ""
        elif tag == "span":
            self._in_span = True
            self._current_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._current_section = self._current_text.strip()
            self._pairs.setdefault(self._current_section, [])
            self._span_texts = []
        elif tag == "span":
            self._in_span = False
            self._span_texts.append(self._current_text.strip())
            self._current_text = ""
        elif tag == "li":
            if len(self._span_texts) >= 2 and self._current_section:
                key = self._span_texts[0]
                value = self._span_texts[1]
                self._pairs[self._current_section].append((key, value))
            self._span_texts = []

    def handle_data(self, data: str) -> None:
        self._current_text += data

    @property
    def sections(self) -> Dict[str, List[Tuple[str, str]]]:
        return self._pairs


def _find_section(sections: Dict[str, List[Tuple[str, str]]], *keywords: str) -> List[Tuple[str, str]]:
    for name, pairs in sections.items():
        lower = name.lower()
        if all(kw.lower() in lower for kw in keywords):
            return pairs
    return []


def _extract_int(text: str) -> Optional[int]:
    text = text.replace(",", "").replace("\xa0", "").strip()
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _extract_pct(text: str) -> Optional[float]:
    m = re.search(r"([\d.]+)\s*%", text)
    return float(m.group(1)) if m else None


def _sum_sensor_counts(text: str) -> int:
    return sum(int(m.group(1)) for m in _COUNT_RE.finditer(text))


def _safe_int(value: Any) -> Optional[int]:
    """Coerce a JSON value to int, returning None on failure."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_json_status(text: str) -> Optional[Dict[str, Any]]:
    """Parse the JSON-format ``Status Data.htm`` from support bundles."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    up = _safe_int(data.get("UpSens")) or 0
    warn = _safe_int(data.get("WarnSens")) or 0
    paused = _safe_int(data.get("PausedSens")) or 0
    unknown = _safe_int(data.get("UnknownSens")) or 0
    alarms = _safe_int(data.get("Alarms")) or 0
    down = _safe_int(data.get("DownSens")) or 0
    total = up + warn + paused + unknown + alarms + down

    if total == 0:
        return None

    result: Dict[str, Any] = {
        "total_sensors": total,
        "sensors_up": up,
        "sensors_warning": warn,
        "sensors_paused": paused,
        "sensors_unknown": unknown,
        "sensors_down": alarms + down,
        "prtg_version": data.get("Version"),
        "source_format": "json",
    }
    return result


def _parse_html_status(html_text: str) -> Optional[Dict[str, Any]]:
    """Parse the HTML-format ``PRTG Status Data.htm`` from support bundles."""
    try:
        parser = _SectionExtractor()
        parser.feed(html_text)
        sections = parser.sections
    except Exception:
        return None

    result: Dict[str, Any] = {}

    # English: "Software Version and Server Information"
    # German:  "Softwareversion und Serverinformation"
    sw_pairs = (
        _find_section(sections, "Software Version")
        or _find_section(sections, "Server Information")
        or _find_section(sections, "Softwareversion")
        or _find_section(sections, "Serverinformation")
    )
    for key, val in sw_pairs:
        key_lower = key.lower()
        if "cpu load" in key_lower or "cpu-last des servers" in key_lower:
            result["server_cpu_load_pct"] = _extract_pct(val)

    # English: "Database Objects"
    # German:  "Objekte in der Datenbank"
    db_pairs = _find_section(sections, "Database Objects") or _find_section(sections, "Objekte in der Datenbank")
    for key, val in db_pairs:
        lower = key.lower().strip()
        if lower in ("sensors", "sensoren"):
            result["total_sensors"] = _extract_int(val)
        elif lower == "probes":
            result["probes"] = _extract_int(val)
        elif lower in ("devices", "geräte"):
            result["devices"] = _extract_int(val)
        elif lower in ("groups", "gruppen"):
            result["groups"] = _extract_int(val)
        elif lower in ("channels", "kanäle"):
            result["channels"] = _extract_int(val)
        elif lower in ("requests/second", "anfragen/sekunde"):
            result["requests_per_second"] = _extract_int(val)

    # English: "Web Server Activity"
    # German:  "Aktivität des Webservers"
    web_pairs = _find_section(sections, "Web Server Activity") or _find_section(sections, "Aktivität des Webservers")
    for key, val in web_pairs:
        if "Slow Request Ratio" in key:
            result["slow_request_ratio_pct"] = _extract_pct(val)
        elif key.strip() == "HTTP Requests > 500 ms":
            result["http_requests_gt_500ms_pct"] = _extract_pct(val)
        elif key.strip() == "HTTP Requests > 1000 ms":
            result["http_requests_gt_1000ms_pct"] = _extract_pct(val)
        elif key.strip() == "HTTP Requests > 5000 ms":
            result["http_requests_gt_5000ms_pct"] = _extract_pct(val)

    # English: "Sensors Sorted by Impact on System Performance"
    # German:  "Sensoren nach Auswirkung auf die Systemleistung"
    impact_pairs = _find_section(sections, "Impact on System Performance") or _find_section(
        sections, "Auswirkung auf die Systemleistung"
    )
    impact_dist: Dict[str, Dict[str, Any]] = {}
    impact_has_data = False
    for key, val in impact_pairs:
        key_text = re.sub(r"<[^>]+>", "", key).strip()
        key_norm = key_text.lower()
        normalized = _IMPACT_LOWER.get(key_norm) or _IMPACT_ALIASES.get(key_norm)
        if normalized:
            total = _sum_sensor_counts(val)
            sensors: Dict[str, int] = {}
            for m in re.finditer(r"(\d+)x\s+([\w._ -]+)", val):
                sensors[m.group(2).strip()] = int(m.group(1))
            if total > 0 or sensors:
                impact_has_data = True
            impact_dist[normalized] = {"total": total, "sensors": sensors}
    for level in _IMPACT_LEVELS:
        impact_dist.setdefault(level, {"total": 0, "sensors": {}})
    result["impact_distribution"] = impact_dist

    has_data = any(
        k != "impact_distribution" and v is not None
        for k, v in result.items()
    )
    if not has_data and not impact_has_data:
        return None

    result["source_format"] = "html"
    return result


def parse_status_data(path: Path) -> Optional[Dict[str, Any]]:
    """Parse a PRTG Status Data file (HTML or JSON) and return a snapshot dict, or None on failure."""
    try:
        raw = path.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            return None
    except Exception:
        return None

    stripped = text.lstrip()
    if stripped.startswith("{"):
        return _parse_json_status(text)

    return _parse_html_status(text)
