# PRTG Performance Analyzer — Fast, Accurate Core.log Analysis for Support & NOC

**Share this with your team: a single-file tool that turns a PRTG Core.log into an actionable, sci-fi style dashboard in minutes.**

---

## What It Does

The **PRTG Performance Analyzer v1.0f** is a standalone desktop application (Windows EXE) that analyzes **only your PRTG Core.log**. No Status Data HTML, no manual exports — just drop the log file and get a full health assessment.

It streams through the log (even very large files), extracts server info, license and hardware details, sensor and probe distribution, impact levels, scan intervals, errors, restarts, and startup metrics. Then it scores the instance (0–100), applies Paessler's recommended thresholds, and presents everything in an interactive dashboard with charts, gauges, and exportable reports.

---

## Strengths

- **Single input** — Only Core.log is required; no dependency on PRTG's web UI or Status Data.
- **Built for real workloads** — Designed for production logs (hundreds of MB, months of data). Parsing is streaming and memory-efficient so it won't run out of memory.
- **Aligned with best practices** — Rules and thresholds are based on the official PRTG setup guide, so findings and recommendations match what Paessler recommends.
- **Ready for support & NOC** — Built for tech support analysts and NOC operators: at-a-glance health, clear severity (Healthy / Optimization Needed / Critical), and drill-down into probes, impact, and top errors.
- **Self-contained** — One EXE; no Python or extra installs on the target machine. Runs a local web server; you open it in your browser on `http://127.0.0.1:8077`.

---

## What It's Capable Of

- **Global snapshot** — Server name, PRTG version, OS, CPU (incl. CPU splitting status), RAM, storage, license owner, timezone, data and system paths.
- **Health score (0–100)** — With deductions for CPU/RAM sizing, OS age, startup time, XML load, errors, sensors per probe, intervals, restarts, long-running threads, impact distribution, and more.
- **Findings** — Categorized by severity (Critical / Warning / Info) with evidence values and concrete recommendations. Recommendation tone scales with severity ("Consider…" vs "Immediate action required…").
- **Top errors** — Most frequent non-license ERRR patterns, with occurrence counts, first/last seen timestamps, sample log lines, and short explanations.
- **Sensors & probes** — Per-probe sensor counts, ERP, impact breakdown, and interval distribution; refresh-rate and sensor-type charts.
- **Timeline** — Restart events and milestones plotted over time to spot instability and correlate with errors.
- **Timeframe filter** — Narrow the score, findings, and error view to the last N restart cycles for focused incident analysis.
- **Export** — Download full JSON or a standalone HTML report for sharing with customers or management.

The dashboard includes multiple charts (stability radar, ERP load gauge, RAM utilization, impact distribution, error activity over time, ERP hot probes) so you can see load, risk, and bottlenecks at a glance.

---

## Speed and Accuracy

- **Speed** — Large Core.log files (e.g. 500 MB+) are processed efficiently thanks to stream parsing and live progress feedback. Results are cached by file hash so re-opening the same log is instant.
- **Accuracy** — Parsing follows the actual Core.log line formats (timestamps, objects summary, probe and impact lines, intervals, errors, etc.). The rules engine uses fixed thresholds from the setup guide with a small tolerance band.

---

## How to Use It

1. Run **PRTG_Analyzerv1.0f.exe** (or the version you received).
2. Open **http://127.0.0.1:8077** in your browser.
3. Drag and drop your **Core.log** (or `.gz`) onto the upload area.
4. Wait for analysis to finish; the dashboard appears with all tabs and charts.
5. Use the **Timeframe** filter to focus on a specific restart window if needed.
6. Use **Export** to download JSON or the HTML report to share results.

The app runs locally only (localhost); no data is sent to external servers. Ideal for secure environments and quick health checks during support cases.
