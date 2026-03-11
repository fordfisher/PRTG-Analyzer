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
def build_enterprise_html_report(result: Dict[str, Any], errors_time_frame: Optional[str] = None) -> str:
    core = result.get("core", {}) or {}
    findings = result.get("findings", []) or []
    if errors_time_frame:
        top_errors = aggregate_top_errors_for_timeframe(core, errors_time_frame)
    else:
        top_errors = (core.get("top_errors") or [])[:10]
    if not top_errors:
        top_errors = []
    if errors_time_frame == "all" or not errors_time_frame:
        errors_card_title = "Top Errors (All)"
    elif errors_time_frame and errors_time_frame.isdigit():
        n = int(errors_time_frame)
        errors_card_title = f"Top Errors (Past {n} restart{'s' if n > 1 else ''})"
    else:
        errors_card_title = "Top Errors (evidence)"
    rr = result.get("refresh_rate_distribution", []) or []
    timeline = result.get("timeline", []) or []

    # redact license key in report payload
    if isinstance(core, dict) and "license_key" in core:
        core = dict(core)
        core["license_key"] = _mask_license_key(str(core.get("license_key") or ""))
        result = dict(result)
        result["core"] = core

    payload_json = json.dumps(
        {
            "core": {"global_impact_distribution": core.get("global_impact_distribution", {})},
            "refresh_rate_distribution": rr,
        },
        ensure_ascii=False,
    )

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
      <div class="card" style="grid-column:span 6">
        <h2>Global Impact Distribution</h2>
        <div id="chartImpact" class="chart"></div>
      </div>
      <div class="card" style="grid-column:span 6">
        <h2>Refresh Rate Distribution</h2>
        <div id="chartRefresh" class="chart"></div>
      </div>
      <div class="card" style="grid-column:span 12">
        <h2>Findings & Recommendations</h2>
        <div style="display:grid;gap:10px">
          {''.join(_finding_html(f) for f in findings) if findings else '<div class="finding">No findings produced.</div>'}
        </div>
      </div>
      <div class="card" style="grid-column:span 12">
        <h2>{_html_escape(errors_card_title)}</h2>
        {''.join(_error_html(e) for e in top_errors) if top_errors else '<div class="finding">No errors parsed.</div>'}
      </div>
    </div>
  </div>

  <script>
    const RESULT = {payload_json};
    const core = RESULT.core || {{}};

    // Impact donut
    (() => {{
      const el = document.getElementById('chartImpact');
      const chart = echarts.init(el);
      const dist = core.global_impact_distribution || {{}};
      const data = Object.keys(dist).map(k => ({{ name: k, value: (dist[k] && dist[k].total) ? dist[k].total : 0 }}));
      chart.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{ trigger: 'item' }},
        legend: {{ textStyle: {{ color: '#b4c6ff' }} }},
        series: [{{ type: 'pie', radius: ['45%','70%'], label: {{ color: '#e4f0ff' }}, data }}]
      }});
    }})();

    // Refresh rate bar
    (() => {{
      const el = document.getElementById('chartRefresh');
      const chart = echarts.init(el);
      const rr = RESULT.refresh_rate_distribution || [];
      chart.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{ trigger: 'axis' }},
        xAxis: {{ type: 'category', data: rr.map(b => b.interval_label), axisLabel: {{ color: '#b4c6ff', rotate: 25 }} }},
        yAxis: {{ type: 'value', axisLabel: {{ color: '#b4c6ff' }} }},
        series: [{{ type: 'bar', data: rr.map(b => b.count), itemStyle: {{ color: '#00ff9c' }} }}]
      }});
    }})();
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

