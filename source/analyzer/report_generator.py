from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .analysis import aggregate_top_errors_for_timeframe
from .version import ANALYZER_VERSION

# Inline echarts for standalone report (no CDN dependency when saved)
_ECHARTS_INLINE: str | None = None


def _get_echarts_script() -> str:
    """Return a <script> tag for echarts: inline if available, else CDN."""
    global _ECHARTS_INLINE
    if _ECHARTS_INLINE is not None:
        return _ECHARTS_INLINE
    # Prefer next to this module (works from any cwd / exe); then project frontend; then PyInstaller bundle
    module_dir = Path(__file__).resolve().parent
    candidates = [
        module_dir / "vendor" / "echarts.min.js",
        module_dir.parent / "frontend" / "vendor" / "echarts.min.js",
    ]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS) / "frontend" / "vendor" / "echarts.min.js")
    for path in candidates:
        try:
            if path.exists():
                raw = path.read_text(encoding="utf-8", errors="replace")
                # Escape so </script> in JS does not close the tag
                escaped = raw.replace("</script>", "<\\/script>")
                _ECHARTS_INLINE = f'<!-- echarts: inline (standalone) -->\n<script>{escaped}</script>'
                return _ECHARTS_INLINE
        except Exception:
            continue
    _ECHARTS_INLINE = '<!-- echarts: cdn (save may break charts) -->\n<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
    return _ECHARTS_INLINE


def _mask_license_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 12:
        return "***"
    return f"{k[:6]}…{k[-4:]}"


def _cpu_splitting_report_html(core: Dict[str, Any]) -> str:
    active = core.get("cpu_splitting_active") is True
    total = core.get("cpu_total_for_splitting") or core.get("cpu_count") or 0
    assigned = core.get("cpu_assigned") or total
    if not active and total == 0:
        return ""
    status = (
        f"Active ({assigned}/{total})"
        if active
        else f"Inactive (all {total} cores used)"
    )
    rec = ""
    if active and total > 8:
        rec = (
            '<div class="kv"><div class="k">Recommendation</div><div style="color:#eab308">'
            "Disable CPU splitting when using more than 8 CPUs; ensure all active cores are on the same physical socket.</div></div>"
        )
    return f'<div class="kv"><div class="k">CPU splitting</div><div>{_html_escape(status)}</div></div>{rec}'
def _parse_errors_timeframes(errors_time_frame: Optional[str]) -> list[str]:
    if not errors_time_frame:
        return []
    raw = str(errors_time_frame).strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    # Normalize and dedupe while preserving order
    out: list[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out


def _filter_top_errors_by_patterns(top_errors: list[Dict[str, Any]], include_error_patterns: Optional[list[str]]) -> list[Dict[str, Any]]:
    if not include_error_patterns:
        return top_errors
    wanted = {str(p) for p in include_error_patterns if str(p).strip()}
    if not wanted:
        return top_errors
    return [e for e in top_errors if str(e.get("pattern", "")) in wanted]


def _errors_title_for_timeframe(tf: str) -> str:
    if tf == "all":
        return "Top Errors (All)"
    if tf.isdigit():
        n = int(tf)
        return f"Top Errors (Past {n} restart{'s' if n > 1 else ''})"
    return "Top Errors (evidence)"


# Chart id -> (title, div_id) for report cards
_REPORT_CHART_META: Dict[str, tuple[str, str]] = {
    "impact-donut": ("Global Impact Distribution", "chartImpact"),
    "refresh-rate": ("Refresh Rate Distribution", "chartRefresh"),
    "stability-radar": ("Stability Radar", "chartStabilityRadar"),
    "erp-orbit": ("ERP Load Orbit", "chartErpOrbit"),
    "ram-usage": ("Memory Utilization", "chartRamUsage"),
    "erp-hot-probes": ("ERP Hot Probes", "chartErpHotProbes"),
    "intervals": ("Refresh Intervals", "chartIntervals"),
    "sensor-types": ("Sensor Type Distribution", "chartSensorTypes"),
    "timeline": ("Timeline", "chartTimeline"),
}


def _build_charts_grid_html(want_charts: set[str], core: Dict[str, Any]) -> str:
    parts = []
    probes_by_id = {int(p.get("probe_id", -1)): p for p in (core.get("probes") or []) if p and p.get("probe_id") is not None}
    # Static charts: full width for bar/list-style (erp-hot-probes, intervals, sensor-types, timeline), half for rest
    full_width_charts = {"erp-hot-probes", "intervals", "sensor-types", "timeline"}
    static_order = list(_REPORT_CHART_META.keys())
    for cid in static_order:
        if cid not in want_charts:
            continue
        meta = _REPORT_CHART_META.get(cid)
        if not meta:
            continue
        title, div_id = meta
        span = 12 if cid in full_width_charts else 6
        parts.append(
            f'<div class="card" style="grid-column:span {span}">'
            f"<h2>{_html_escape(title)}</h2>"
            f'<div id="{_html_escape(div_id)}" class="chart"></div>'
            f"</div>"
        )
    probe_ids = []
    for cid in want_charts:
        if not cid.startswith("probe-impact-"):
            continue
        try:
            probe_id = int(cid.replace("probe-impact-", "", 1))
            if probe_id in probes_by_id:
                probe_ids.append(probe_id)
        except ValueError:
            pass
    for probe_id in sorted(probe_ids):
        probe = probes_by_id[probe_id]
        title = f"Probe: {probe.get('name') or ('Probe ' + str(probe_id))}"
        div_id = f"chartProbeImpact{probe_id}"
        parts.append(
            f'<div class="card" style="grid-column:span 12">'
            f"<h2>{_html_escape(title)}</h2>"
            f'<div id="{_html_escape(div_id)}" class="chart"></div>'
            f"</div>"
        )
    return "\n      ".join(parts) if parts else ""


def _build_charts_script(want_charts: set[str]) -> str:
    """Return JavaScript that inits only the requested charts. Uses RESULT, core, rr, etc."""
    blocks = []
    core_js = "const core = RESULT.core || {};"
    rr_js = "const rr = RESULT.refresh_rate_distribution || [];"
    if "impact-donut" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartImpact');
      if (!el) return;
      const chart = echarts.init(el);
      const dist = core.global_impact_distribution || {};
      const data = Object.keys(dist).map(k => ({ name: k, value: (dist[k] && dist[k].total) ? dist[k].total : 0 }));
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: { textStyle: { color: '#b4c6ff' } },
        series: [{ type: 'pie', radius: ['45%','70%'], label: { color: '#e4f0ff' }, data }]
      });
    })();"""
        )
    if "refresh-rate" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartRefresh');
      if (!el) return;
      const chart = echarts.init(el);
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: rr.map(b => b.interval_label), axisLabel: { color: '#b4c6ff', rotate: 25 } },
        yAxis: { type: 'value', axisLabel: { color: '#b4c6ff' } },
        series: [{ type: 'bar', data: rr.map(b => b.count), itemStyle: { color: '#00ff9c' } }]
      });
    })();"""
        )
    if "stability-radar" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartStabilityRadar');
      if (!el) return;
      const chart = echarts.init(el);
      const clamp = (x, a, b) => Math.max(a, Math.min(b, Number(x) || 0));
      const values = [
        clamp((Number(core.total_errors || 0) + Number(core.total_warnings || 0)) / 10, 0, 100),
        clamp(Number(core.total_restarts || 0) * 10, 0, 100),
        clamp((Number(core.startup_duration_sec || 0) / 60) * 20, 0, 100),
        clamp((Number(core.max_thread_runtime || 0) / 60) * 10, 0, 100),
        clamp(Number(RESULT.calculated_requests_per_min || 0) / 150, 0, 100)
      ];
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        radar: {
          indicator: [
            { name: 'Errors', max: 100 },
            { name: 'Restarts', max: 100 },
            { name: 'Startup', max: 100 },
            { name: 'Threads', max: 100 },
            { name: 'Load', max: 100 }
          ],
          splitArea: { areaStyle: { color: ['rgba(8,20,40,0.9)', 'rgba(5,17,35,0.9)'] } },
          axisName: { color: '#b4c6ff' }
        },
        series: [{ type: 'radar', areaStyle: { opacity: 0.35 }, lineStyle: { color: '#22c55e' }, itemStyle: { color: '#22c55e' }, data: [{ value: values, name: 'Risk' }] }]
      });
    })();"""
        )
    if "erp-orbit" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartErpOrbit');
      if (!el) return;
      const chart = echarts.init(el);
      const rpm = Number(RESULT.calculated_requests_per_min || 0);
      const safeTotal = (Number(core.total_probes || 0) || 1) * 10000;
      const loadPct = Math.max(0, Math.min(200, safeTotal > 0 ? (rpm * 100) / safeTotal : 0));
      const color = loadPct > 150 ? '#ef4444' : loadPct > 100 ? '#eab308' : '#22c55e';
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { formatter: () => 'Load: ' + rpm.toFixed(0) + ' req/min' },
        series: [{
          type: 'gauge',
          startAngle: 200, endAngle: -20, min: 0, max: 200,
          axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(34,197,94,0.4)']] } },
          progress: { show: true, width: 10, itemStyle: { color } },
          pointer: { show: false },
          axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
          detail: { formatter: () => loadPct.toFixed(0) + '% load', color: '#e4f0ff', fontSize: 16 },
          data: [{ value: loadPct }]
        }]
      });
    })();"""
        )
    if "ram-usage" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartRamUsage');
      if (!el) return;
      const chart = echarts.init(el);
      const total = Number(core.total_ram_mb || 0);
      const free = Number(core.free_ram_mb || 0);
      const usedPct = total > 0 ? Math.max(0, Math.min(100, ((total - free) * 100) / total)) : 0;
      const color = usedPct > 90 ? '#ef4444' : usedPct > 75 ? '#eab308' : '#22c55e';
      chart.setOption({
        backgroundColor: 'transparent',
        series: [{
          type: 'gauge',
          startAngle: 210, endAngle: -30, min: 0, max: 100,
          axisLine: { lineStyle: { width: 8, color: [[1, 'rgba(15,23,42,0.9)']] } },
          progress: { show: true, width: 8, itemStyle: { color } },
          pointer: { show: false },
          axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
          detail: { formatter: () => usedPct.toFixed(0) + '% used', color: '#e4f0ff', fontSize: 14 },
          data: [{ value: usedPct }]
        }]
      });
    })();"""
        )
    if "erp-hot-probes" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartErpHotProbes');
      if (!el) return;
      const chart = echarts.init(el);
      const probes = (RESULT.probes_by_erp || []).slice(0, 8);
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 120, right: 16, top: 20, bottom: 32 },
        xAxis: { type: 'value', axisLabel: { color: '#b4c6ff' } },
        yAxis: { type: 'category', data: probes.map(function(p) { return p.name || ''; }), axisLabel: { color: '#b4c6ff' } },
        series: [{ type: 'bar', data: probes.map(function(p) { return Number(p.erp || 0); }), itemStyle: { color: '#3b82f6' } }]
      });
    })();"""
        )
    if "intervals" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartIntervals');
      if (!el) return;
      const chart = echarts.init(el);
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: rr.map(function(b) { return b.interval_label; }), axisLabel: { color: '#b4c6ff', rotate: 30 } },
        yAxis: { type: 'value', name: 'Sensor count', nameTextStyle: { color: '#9fb5ff' }, axisLabel: { color: '#b4c6ff' } },
        series: [{ type: 'bar', data: rr.map(function(b) { return b.count; }), itemStyle: { color: '#00ff9c' } }]
      });
    })();"""
        )
    if "sensor-types" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartSensorTypes');
      if (!el) return;
      const chart = echarts.init(el);
      const st = RESULT.sensor_type_distribution || [];
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 120, right: 20, top: 20, bottom: 40 },
        xAxis: { type: 'value', name: 'Sensor count', nameTextStyle: { color: '#9fb5ff' }, axisLabel: { color: '#b4c6ff' } },
        yAxis: { type: 'category', data: st.map(function(e) { return e.name; }), axisLabel: { color: '#b4c6ff' } },
        series: [{ type: 'bar', data: st.map(function(e) { return e.value; }), itemStyle: { color: '#ff6b6b' } }]
      });
    })();"""
        )
    if "timeline" in want_charts:
        blocks.append(
            """
    (() => {
      const el = document.getElementById('chartTimeline');
      if (!el) return;
      const chart = echarts.init(el);
      const timeline = RESULT.timeline || [];
      const points = timeline.filter(function(p) { return p && p.timestamp; }).map(function(p) {
        return [p.timestamp, p.kind === 'restart' ? 1 : 0, p.label || ''];
      });
      chart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item', formatter: function(params) { return params.value[0] + '<br/>' + params.value[2]; } },
        xAxis: { type: 'time', axisLabel: { color: '#b4c6ff' } },
        yAxis: { type: 'value', min: -0.5, max: 1.5, axisLabel: { show: false }, splitLine: { show: false } },
        series: [{ type: 'scatter', symbolSize: 10, data: points, itemStyle: { color: '#7df9ff' } }]
      });
    })();"""
        )
    probe_impact_ids = []
    for cid in want_charts:
        if cid.startswith("probe-impact-"):
            try:
                probe_impact_ids.append(int(cid.replace("probe-impact-", "", 1)))
            except ValueError:
                pass
    if probe_impact_ids:
        probe_impact_ids = sorted(probe_impact_ids)
        blocks.append(
            """
    (function() {
      var probeImpactIds = """
            + json.dumps(probe_impact_ids)
            + """;
      var IMPACT_ORDER = ['Very low', 'Low', 'Medium', 'High', 'Very High'];
      var IMPACT_COLORS = { 'Very low': '#22c55e', 'Low': '#00ff9c', 'Medium': '#eab308', 'High': '#ff6b6b', 'Very High': '#ef4444' };
      function buildProbeBars(dist) {
        var entries = [];
        IMPACT_ORDER.forEach(function(level) {
          var levelData = dist[level] || {};
          var sensors = levelData.sensors || {};
          Object.keys(sensors).forEach(function(sensorType) {
            var n = Number(sensors[sensorType]) || 0;
            if (n > 0) entries.push({ name: sensorType, impact: level, value: n });
          });
        });
        entries.sort(function(a, b) {
          var ai = IMPACT_ORDER.indexOf(a.impact);
          var bi = IMPACT_ORDER.indexOf(b.impact);
          if (ai !== bi) return ai - bi;
          return (a.name || '').localeCompare(b.name || '');
        });
        var categories = entries.map(function(e) { return e.name; });
        var barData = entries.map(function(e) { return { value: e.value, itemStyle: { color: IMPACT_COLORS[e.impact] || '#b4c6ff' } }; });
        return { categories: categories, barData: barData };
      }
      var probes = (RESULT.core && RESULT.core.probes) || [];
      probeImpactIds.forEach(function(probeId) {
        var el = document.getElementById('chartProbeImpact' + probeId);
        if (!el) return;
        var probe = probes.find(function(p) { return Number(p.probe_id) === probeId; });
        if (!probe) return;
        var out = buildProbeBars(probe.impact_distribution || {});
        var chart = echarts.init(el);
        chart.setOption({
          backgroundColor: 'transparent',
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 72, right: 16, top: 20, bottom: 32 },
          xAxis: { type: 'category', data: out.categories, axisLabel: { color: '#b4c6ff' } },
          yAxis: { type: 'value', axisLabel: { color: '#b4c6ff' } },
          series: [{ type: 'bar', data: out.barData }]
        });
      });
    })();"""
        )
    return (core_js + "\n    " + rr_js + "\n    " + "\n    ".join(blocks)).strip()


def _sensor_type_distribution_from_core(core: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Build [{ name, value }] from core.global_impact_distribution for report sensor-types chart."""
    counts: Dict[str, int] = {}
    for info in (core.get("global_impact_distribution") or {}).values():
        if not isinstance(info, dict):
            continue
        for sensor_type, count in (info.get("sensors") or {}).items():
            n = int(count) if count is not None else 0
            if n > 0:
                counts[sensor_type] = counts.get(sensor_type, 0) + n
    return sorted(
        [{"name": k, "value": v} for k, v in counts.items()],
        key=lambda x: -x["value"],
    )[:20]


def _build_report_chart_payload(
    result: Dict[str, Any],
    core: Dict[str, Any],
    rr: list[Dict[str, Any]],
    timeline: list[Dict[str, Any]],
    include_charts: Optional[list[str]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "core": {"global_impact_distribution": core.get("global_impact_distribution", {})},
        "refresh_rate_distribution": rr,
    }
    if include_charts is None:
        return payload

    payload["core"] = dict(core)
    payload["timeline"] = timeline
    payload["calculated_requests_per_min"] = result.get("calculated_requests_per_min")
    payload["sensor_type_distribution"] = _sensor_type_distribution_from_core(core)
    payload["probes_by_erp"] = sorted(
        [
            {"name": probe.get("name", ""), "erp": probe.get("erp", 0)}
            for probe in (core.get("probes") or [])
            if probe and probe.get("erp") is not None
        ],
        key=lambda entry: -(entry.get("erp") or 0),
    )
    return payload


def build_enterprise_html_report(
    result: Dict[str, Any],
    errors_time_frame: Optional[str] = None,
    include_error_patterns: Optional[list[str]] = None,
    include_charts: Optional[list[str]] = None,
    include_findings: bool = True,
    include_finding_indices: Optional[list[int]] = None,
) -> str:
    core = result.get("core", {}) or {}
    all_findings = result.get("findings", []) or []
    if include_finding_indices is not None:
        findings = [all_findings[i] for i in include_finding_indices if 0 <= i < len(all_findings)]
    else:
        findings = all_findings
    tfs = _parse_errors_timeframes(errors_time_frame)
    if not tfs:
        # Backward compatible default: "All" (or evidence fallback from core.top_errors)
        top_errors = (core.get("top_errors") or [])[:10]
        top_errors = _filter_top_errors_by_patterns(top_errors, include_error_patterns)
        errors_sections_html = f"""
      <div class="card" style="grid-column:span 12">
        <h2>Top Errors (All)</h2>
        {''.join(_error_html(e) for e in top_errors) if top_errors else '<div class="finding">No errors parsed.</div>'}
      </div>
"""
    else:
        sections = []
        for tf in tfs:
            top_errors = aggregate_top_errors_for_timeframe(core, tf)
            top_errors = _filter_top_errors_by_patterns(top_errors, include_error_patterns)
            title = _errors_title_for_timeframe(tf)
            sections.append(
                f"""
      <div class="card" style="grid-column:span 12">
        <h2>{_html_escape(title)}</h2>
        {''.join(_error_html(e) for e in top_errors) if top_errors else '<div class="finding">No errors in this tier.</div>'}
      </div>
"""
            )
        errors_sections_html = "".join(sections)
    rr = result.get("refresh_rate_distribution", []) or []
    timeline = result.get("timeline", []) or []

    # Charts to include: default = only impact-donut and refresh-rate (backward compatible)
    chart_ids = include_charts if include_charts is not None else ["impact-donut", "refresh-rate"]
    want_charts = set(chart_ids)

    # redact license key in report payload
    if isinstance(core, dict) and "license_key" in core:
        core = dict(core)
        core["license_key"] = _mask_license_key(str(core.get("license_key") or ""))
        result = dict(result)
        result["core"] = core

    payload = _build_report_chart_payload(result, core, rr, timeline, include_charts)
    payload_json = json.dumps(payload, ensure_ascii=False)

    charts_grid_html = _build_charts_grid_html(want_charts, core)
    charts_script = _build_charts_script(want_charts)

    findings_section_html = ""
    if findings:
        findings_section_html = f"""
      <div class="card" style="grid-column:span 12">
        <h2>Findings & Recommendations</h2>
        <div style="display:flex;flex-direction:column;gap:10px">
          {''.join(_finding_html(f) for f in findings)}
        </div>
      </div>"""

    title = f"PyPRTG_CLA Enterprise Report — {core.get('server_name') or 'Unknown'}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{_html_escape(title)}</title>
  {_get_echarts_script()}
  <style>
    html,body{{margin:0;padding:0;background:#050814;color:#e4f0ff;font-family:Segoe UI,system-ui,sans-serif;}}
    .wrap{{max-width:1200px;margin:0 auto;padding:28px 22px;}}
    .hero{{padding:18px 18px;border:1px solid rgba(125,249,255,.35);border-radius:16px;background:linear-gradient(145deg,rgba(8,20,40,.92),rgba(4,8,20,.96));box-shadow:0 18px 45px rgba(0,0,0,.85),0 0 40px rgba(0,240,255,.18);}}
    h1{{margin:0 0 6px 0;letter-spacing:.12em;text-transform:uppercase;color:#7df9ff;font-size:18px;}}
    .grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px;}}
    .card{{grid-column:span 6;padding:14px 14px;border:1px solid rgba(125,249,255,.25);border-radius:14px;background:rgba(0,0,0,.18);}}
    .card h2{{margin:0 0 10px 0;font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#aee4ff;}}
    .kvs{{display:grid;gap:6px;}}
    .kv{{display:flex;gap:10px;}}
    .k{{width:160px;opacity:.8}}
    .chart{{height:320px;border-radius:14px;border:1px solid rgba(120,240,255,.25);background:rgba(0,0,0,.18);}}
    .finding{{padding:12px;border-radius:12px;border:1px solid rgba(125,249,255,.25);background:rgba(0,0,0,.18);}}
    .sev-red{{border-color:rgba(255,77,109,.45);}}
    .sev-yellow{{border-color:rgba(255,209,102,.45);}}
    .sev-green{{border-color:rgba(0,255,156,.35);}}
    pre{{white-space:pre-wrap;word-break:break-word;background:rgba(0,0,0,.25);padding:10px;border-radius:12px;border:1px solid rgba(125,249,255,.15);}}
    @media (max-width: 900px){{.card{{grid-column:span 12;}}}}

    /* Manual PDF from HTML: A4, pagination (break-inside: avoid), PyPRTG_CLA design preserved in print */
    @page {{ size: A4; margin: 12mm; }}
    @media print {{
      html,body{{ background:#fff !important; color:#000 !important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
      .wrap{{ max-width:none; margin:0; padding:0; }}
      .hero{{ background:#fff !important; box-shadow:none !important; border-color:#bbb !important; }}
      h1{{ color:#000 !important; }}
      .card{{ background:#fff !important; border-color:#cfcfcf !important; box-shadow:none !important; break-inside:avoid; page-break-inside:avoid; }}
      .card h2{{ color:#000 !important; }}
      .finding{{ background:#fff !important; border-color:#cfcfcf !important; break-inside:avoid; page-break-inside:avoid; }}
      .sev-red{{ border-color:#d11a2a !important; }}
      .sev-yellow{{ border-color:#b97800 !important; }}
      .sev-green{{ border-color:#1a7f37 !important; }}
      .chart{{ border-color:#cfcfcf !important; background:#fff !important; break-inside:avoid; page-break-inside:avoid; }}
      pre{{ background:#f6f6f6 !important; border-color:#dedede !important; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>{_html_escape(title)}</h1>
      <div style="opacity:.9">Generated by PyPRTG_CLA v{ANALYZER_VERSION} — standalone report</div>
      <div class="grid" style="margin-top:14px">
        <div class="card">
          <h2>Global Snapshot</h2>
          <div class="kvs">
            <div class="kv"><div class="k">Server</div><div><b>{_html_escape(core.get("server_name",""))}</b></div></div>
            <div class="kv"><div class="k">License owner</div><div><b>{_html_escape(core.get("license_owner","") or "—")}</b></div></div>
            <div class="kv"><div class="k">SystemID</div><div>{_html_escape(core.get("system_id","") or "—")}</div></div>
            <div class="kv"><div class="k">PRTG Version</div><div>{_html_escape(core.get("prtg_version",""))}</div></div>
            <div class="kv"><div class="k">OS</div><div>{_html_escape(core.get("os_version",""))}</div></div>
            <div class="kv"><div class="k">Sensors / Probes</div><div>{_html_escape(str(core.get("total_sensors","")))} / {_html_escape(str(core.get("total_probes","")) or str(len(core.get("probes") or [])))}</div></div>
            <div class="kv"><div class="k">Score</div><div><b>{_html_escape(str(result.get("score","")))}</b></div></div>
            {_cpu_splitting_report_html(core)}
          </div>
        </div>
        <div class="card">
          <h2>Key Signals</h2>
          <div class="kvs">
            <div class="kv"><div class="k">Errors / Warnings</div><div>{_html_escape(str(core.get("total_errors","")))} / {_html_escape(str(core.get("total_warnings","")))}</div></div>
            <div class="kv"><div class="k">Restarts</div><div>{_html_escape(str(core.get("total_restarts","")))}</div></div>
            <div class="kv"><div class="k">Estimated RPS</div><div>{_html_escape(str(core.get("estimated_requests_per_second","")))}</div></div>
            <div class="kv"><div class="k">Requests/min (calc)</div><div>{_html_escape(str(round(float(result.get("calculated_requests_per_min",0.0)),0)))}</div></div>
            <div class="kv"><div class="k">License owner</div><div>{_html_escape(core.get("license_owner","") or "—")}</div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid" style="margin-top:14px">
      {charts_grid_html}
      {findings_section_html}
      {errors_sections_html}
    </div>
  </div>

  <script>
    const RESULT = {payload_json};
    {charts_script}
  </script>
</body>
</html>
"""


def _finding_html(f: Dict[str, Any]) -> str:
    sev = str(f.get("severity", "info")).lower()
    sev_class = "sev-red" if sev == "red" else "sev-yellow" if sev == "yellow" else "sev-green" if sev == "green" else ""
    evidence = f.get("evidence") or []
    ev_html = "".join(f"<div><small>{_html_escape(e.get('label',''))}:</small> {_html_escape(e.get('value',''))}</div>" for e in evidence)
    return f"""
      <div class="finding {sev_class}">
        <div style="display:flex;justify-content:space-between;gap:10px">
          <div style="font-weight:700">{_html_escape(f.get("title",""))}</div>
          <div style="opacity:.9"><small>{_html_escape(f.get("rule_id",""))} · {_html_escape(str(f.get("score_delta","")))}</small></div>
        </div>
        <div style="margin-top:6px;color:#b4c6ff">{_html_escape(f.get("recommendation",""))}</div>
        <div style="margin-top:8px;display:grid;gap:2px;opacity:.95">{ev_html}</div>
      </div>
    """


def _error_html(e: Dict[str, Any]) -> str:
    samples = e.get("sample_lines") or []
    sample_pre = "\n".join(str(s) for s in samples[:5])
    return f"""
      <div class="finding sev-red" style="margin-top:10px">
        <div style="display:flex;justify-content:space-between;gap:10px">
          <div style="font-weight:700">#{_html_escape(str(e.get("rank","")))} · {_html_escape(str(e.get("count","")))}×</div>
          <div style="opacity:.9"><small>{_html_escape(str(e.get("first_seen","")))} → {_html_escape(str(e.get("last_seen","")))}</small></div>
        </div>
        <div style="margin-top:6px">{_html_escape(str(e.get("pattern","")))}</div>
        <pre>{_html_escape(sample_pre)}</pre>
      </div>
    """


def _html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )

