"""Tests for the PRTG Status Data HTML parser."""
from __future__ import annotations

import tempfile
from pathlib import Path

from analyzer.status_data_parser import parse_status_data


_MINIMAL_STATUS_HTML = """
<html>
<body>
<div class="screenbox">
<h2>Software Version and Server Information</h2>
<ul>
  <li><span>PRTG Version</span><span>PRTG Network Monitor 25.4.114.1032 x64</span></li>
  <li><span>Server CPU Load</span><span>12%</span></li>
</ul>
</div>
<div class="screenbox">
<h2>Database Objects</h2>
<ul>
  <li><span>Probes</span><span>5</span></li>
  <li><span>Groups</span><span>100</span></li>
  <li><span>Devices</span><span>800</span></li>
  <li><span>Sensors</span><span>4500</span></li>
  <li><span>Channels</span><span>15000</span></li>
  <li><span>Requests/Second</span><span>35</span></li>
</ul>
</div>
<div class="screenbox">
<h2>Sensors Sorted by Impact on System Performance</h2>
<ul>
  <li><span>Very low</span><span>100x ping, 50x snmpuptime</span></li>
  <li><span>Low</span><span>200x snmpcpu, 100x snmpmemory</span></li>
  <li><span>Medium</span><span>3000x snmptraffic-V3</span></li>
  <li><span>High</span><span>50x wmiprocess</span></li>
  <li><span>Very high</span><span></span></li>
</ul>
</div>
<div class="screenbox">
<h2>Web Server Activity</h2>
<ul>
  <li><span>Time Since Startup</span><span>2 d 5 h 10 m</span></li>
  <li><span>HTTP Requests</span><span>100000 (50000/24h)</span></li>
  <li><span>HTTP Requests > 500 ms</span><span>5000 (5%)</span></li>
  <li><span>HTTP Requests > 1000 ms</span><span>2000 (2%)</span></li>
  <li><span>HTTP Requests > 5000 ms</span><span>1000 (1%)</span></li>
  <li><span>Slow Request Ratio</span><span> 8%</span></li>
</ul>
</div>
</body>
</html>
"""


def _write_html(content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
        f.write(content)
        return Path(f.name)


def test_parse_minimal_html() -> None:
    path = _write_html(_MINIMAL_STATUS_HTML)
    result = parse_status_data(path)
    assert result is not None

    assert result["server_cpu_load_pct"] == 12.0
    assert result["total_sensors"] == 4500
    assert result["probes"] == 5
    assert result["devices"] == 800
    assert result["requests_per_second"] == 35
    assert result["slow_request_ratio_pct"] == 8.0


def test_parse_impact_distribution() -> None:
    path = _write_html(_MINIMAL_STATUS_HTML)
    result = parse_status_data(path)
    assert result is not None

    impact = result["impact_distribution"]
    assert impact["Very low"]["total"] == 150
    assert impact["Low"]["total"] == 300
    assert impact["Medium"]["total"] == 3000
    assert impact["High"]["total"] == 50
    assert impact["Very high"]["total"] == 0

    assert impact["Very low"]["sensors"]["ping"] == 100
    assert impact["Very low"]["sensors"]["snmpuptime"] == 50
    assert impact["Low"]["sensors"]["snmpcpu"] == 200


def test_parse_empty_impact_levels() -> None:
    path = _write_html(_MINIMAL_STATUS_HTML)
    result = parse_status_data(path)
    assert result is not None
    assert result["impact_distribution"]["Very high"] == {"total": 0, "sensors": {}}


def test_parse_malformed_html_returns_none() -> None:
    path = _write_html("<html><body><p>Not a status page</p></body></html>")
    result = parse_status_data(path)
    assert result is None


def test_parse_nonexistent_file_returns_none() -> None:
    result = parse_status_data(Path("/tmp/does_not_exist_12345.htm"))
    assert result is None


def test_parse_partial_html_still_extracts_available_fields() -> None:
    html = """
    <html><body>
    <div class="screenbox"><h2>Database Objects</h2>
    <ul><li><span>Sensors</span><span>9999</span></li></ul>
    </div>
    </body></html>
    """
    path = _write_html(html)
    result = parse_status_data(path)
    assert result is not None
    assert result["total_sensors"] == 9999
    assert "server_cpu_load_pct" not in result


def test_parse_http_request_percentages() -> None:
    path = _write_html(_MINIMAL_STATUS_HTML)
    result = parse_status_data(path)
    assert result is not None
    assert result["http_requests_gt_500ms_pct"] == 5.0
    assert result["http_requests_gt_1000ms_pct"] == 2.0
    assert result["http_requests_gt_5000ms_pct"] == 1.0
