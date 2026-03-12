# PyPRTG_CLA v1.5.5 — User Manual

> **100% deterministic · 11 hardcoded rules · Runs 100% locally — no data leaves your machine**

---

## Table of Contents

1. [What is PyPRTG_CLA?](#1-what-is-pyprtg_cla)
2. [System Requirements](#2-system-requirements)
3. [Installation & First Launch](#3-installation--first-launch)
4. [Uploading Core.log and Status Data](#4-uploading-corelog-and-status-data)
5. [Tab: Overview](#5-tab-overview)
6. [Tab: Findings](#6-tab-findings)
7. [Tab: Top Errors](#7-tab-top-errors)
8. [Tab: Sensors & Probes](#8-tab-sensors--probes)
9. [Tab: Timeline](#9-tab-timeline)
10. [Tab: System Info](#10-tab-system-info)
11. [Timeframe Filter](#11-timeframe-filter)
12. [Export](#12-export)
13. [Health Score & Rules Engine](#13-health-score--rules-engine)
14. [Reliability & Data Integrity](#14-reliability--data-integrity)
15. [Troubleshooting](#15-troubleshooting)
16. [Privacy & Security](#16-privacy--security)

---

## 1. What is PyPRTG_CLA?

**PyPRTG_CLA** (Python PRTG Core Log Analyzer) is a standalone, local web application built specifically for PRTG Network Monitor. It takes a single `Core.log` file as input, parses every relevant line with deterministic regex patterns, evaluates the extracted data against a set of **11 hardcoded best-practice rules**, computes a 0–100 health score, and presents the results as an interactive browser-based dashboard.

> **Zero AI. Zero guessing.** Every finding, every score delta, every recommendation is produced by explicit, auditable logic. If the data is not in the log, it is not shown. Period.

### Who is it for?

- **Paessler Support Engineers** — instantly assess a customer instance from a single log file, without access to the live PRTG instance.
- **NOC Operators** — quickly understand the health of monitored PRTG servers.
- **PRTG Administrators** — proactively review their own instance against Paessler's official sizing guidelines.

### What does it analyze?

Everything in the main analysis comes *directly* from the log. When a Status Data file is uploaded, an additional Status Snapshot shows live metrics from the bundle.

- Server name, PRTG version, license owner, OS, CPU, RAM, storage paths, timezone
- Total sensors, probes, devices, groups, channels, users
- Sensor impact distribution (five levels: Very Low → Very High)
- Sensor refresh-rate (interval) distribution
- Per-probe sensor counts, ERP (Estimated Requests Per second), and impact breakdown
- All ERRR-level log errors, normalized and deduplicated into patterns
- Restart history and startup milestones
- Thread runtime statistics
- CPU splitting configuration

---

## 2. System Requirements

| Requirement | Details |
|---|---|
| **Operating System** | 64-bit Windows 10 or later |
| **Browser** | Microsoft Edge, Google Chrome, or Mozilla Firefox |
| **Network** | Localhost access — TCP port `8077` must not be blocked |
| **Disk** | Small amount of temp space for the result cache |
| **RAM** | No special requirement — parsing is streaming and memory-efficient |

> **No Python required.** The EXE is fully self-contained.

---

## 3. Installation & First Launch

There is no installation step. The entire application ships as a single file: `PyPRTG_CLA.exe`

### Starting the application

1. Locate `PyPRTG_CLA.exe` and double-click it.
2. If **Windows SmartScreen** shows an "unrecognized app" warning:
   - Click **More info**
   - Then click **Run anyway**
3. A console window opens. The **first launch** may take **5–15 seconds** while PyInstaller unpacks the embedded Python runtime.
4. Wait until the console shows:
   ```
   Uvicorn running on http://127.0.0.1:8077
   ```
5. Open your browser and navigate to: `http://127.0.0.1:8077`

### Stopping the application

- Close the console window, or
- Click into the console and press `Ctrl + C` to stop the server gracefully.

> **Custom port.** If port 8077 is taken, set the environment variable `PRTG_ANALYZER_PORT` to a different number before launching.

### In-app updates

When a newer version is published on GitHub, the app can update itself. In the web UI header, click **Check for updates**. If an update is available, an overlay appears; click **Update now**. The app downloads the new version, restarts, and opens the new instance. The browser page will reload automatically when the new app is ready, or you can click **Reload page** in the overlay.

---

## 4. Uploading Core.log and Status Data

### Core.log (required)

| Format | Extension | Notes |
|---|---|---|
| Plain text log | `.log` | Standard PRTG Core.log |
| Gzip-compressed log | `.gz` | Decompressed transparently on upload |
| Plain text (renamed) | `.txt` | Also accepted |

File encoding is auto-detected: `UTF-8`, `UTF-16`, and `latin-1` are all handled.

### Status Data (optional)

You can optionally upload a **PRTG Status Data** file from the same support bundle. This adds a **Status Snapshot** panel showing live sensor counts and metrics from when the bundle was created (instead of from the last PRTG restart).

| File | Format | What it provides |
|---|---|---|
| `PRTG Status Data.htm` | HTML | Full metrics: CPU load, RPS, slow request ratio, impact distribution |
| `Status Data.htm` | JSON | Sensor status counts: up, warning, down, paused, unknown |

Both formats are auto-detected. If no Status Data file is uploaded, the app works exactly as before — nothing changes.

### How to upload

1. (Optional) Click **Upload Status Data** and select your `.htm` file from the support bundle. The button will show the selected filename.
2. **Upload Core.log**: Drag and drop your `Core.log` onto the upload area, or click it to open a file browser.
3. A **live progress bar** shows parsing status in real time. Large files (hundreds of MB) are processed with a streaming parser — memory usage stays low.
4. When analysis completes, the dashboard appears automatically with all tabs and charts populated.

### Instant re-analysis from cache

Every uploaded file is identified by its **SHA-256 hash**. Re-uploading the same file is instant — results are served from cache. The cache is keyed to the analyzer version, so upgrading PyPRTG_CLA automatically invalidates old cached results and triggers a fresh analysis.

> **Where does PRTG store Core.log?**
> `C:\ProgramData\Paessler\PRTG Network Monitor\Logs\Core\Core.log`

---

## 5. Tab: Overview

The Overview tab is the landing view after a successful analysis.

### View toggle (Now / Historical)

If you uploaded a Status Data file, a **View: Now | Historical** toggle appears above the dashboard. Use it to switch between:

- **Now** — Shows the Status Snapshot panel (live data from the bundle). The time-window slider is hidden.
- **Historical** — Shows the time-window slider. The Status Snapshot panel is visible when the slider is set to "All".

### Status Snapshot panel (when Status Data was uploaded)

This panel shows metrics from the Status Data file (bundle creation time). For **HTML** format: total sensors, CPU load, requests/second, slow request ratio, and sensor impact by level. For **JSON** format: total sensors, up/warning/down counts (color-coded), and PRTG version. When available, values are compared to the last boot from the Core.log.

### Global Snapshot panel

| Field | Description |
|---|---|
| Server name | Hostname of the PRTG server |
| PRTG version | e.g. `26.1.1` |
| License owner | Licensed organization name |
| System ID | Internal PRTG SystemID |
| Total sensors / probes | Counts extracted from the log |
| CPU splitting status | Whether CPU splitting is active |
| Health score | 0–100 with color-coded verdict |

### Instance Health panel

- **Health verdict** — one of: ✅ Healthy, ⚠️ Optimization Needed, or 🔴 Critical
- **Log span days** — calendar range covered by the log file
- **Restart count** — total PRTG Core restarts detected
- **Error and warning pills** — quick count of ERRR and warning lines

### Metrics grid (4 cards)

| Card | Values shown |
|---|---|
| **Load & ERP** | Calculated requests per minute, total ERP from log, busiest probe |
| **Stability** | Restart count, total warning count |
| **License & OS** | License owner, OS version string |
| **Errors** | Total errors, errors in last 24h, errors since last restart |

### Overview charts (6 visualizations)

| Chart | What it shows |
|---|---|
| **Stability Radar** | 5-axis radar: Errors, Restarts, Startup, Threads, Load |
| **ERP Load Orbit** | Gauge: scanning load as % of safe capacity (10,000 req/min) |
| **Memory Utilization** | Gauge: RAM used % of total installed RAM |
| **Sensor Impact Levels** | Donut: distribution across Very Low / Low / Medium / High / Very High |
| **Error Activity Over Time** | Line: daily error volume across the log's time span |
| **ERP Hot Probes** | Horizontal bar: top 8 probes by ERP value |

---

## 6. Tab: Findings

Lists every rule that triggered during analysis. Only rules that actually fire are shown.

Each finding card includes:

- **Title** — plain-language description, color-coded by severity
- **Rule ID** — internal reference (e.g. `RULE_2_RAM`)
- **Score delta** — points deducted from the health score
- **Evidence** — the actual values from the log that triggered the rule
- **Recommendation** — a concrete action with tone scaled to severity:
  - Slightly over threshold → *"Consider…"*
  - Moderately over threshold → *"We recommend…"*
  - Severely over threshold → *"Immediate action required…"*

> All thresholds and recommendations are aligned with **Paessler's official PRTG setup guide**.

See [Section 13](#13-health-score--rules-engine) for the complete list of all 11 rules.

---

## 7. Tab: Top Errors

Shows the most frequently occurring error patterns from all `ERRR`-level lines in the log.

### How errors are processed

Raw error lines are **normalized** before counting, replacing variable parts with placeholders so that many instances of the same underlying error group into a single pattern:

| Variable part | Replaced with |
|---|---|
| GUIDs | `{<guid>}` |
| Thread IDs | `TId <id>` |
| Hexadecimal values | `0x<hex>` |
| Numbers with 2+ digits | `<n>` |

The analyzer stores up to **500 unique error patterns** and surfaces the **top 10** in this tab.

### License errors are excluded

License activation and key-validation errors are **explicitly excluded** from all error counts. These are common, expected, and not indicators of operational problems.

### What each error card shows

- **Rank** — position by frequency (#1 = most frequent)
- **Occurrence count** — exact number of times this pattern appeared
- **First seen / Last seen** — timestamps bounding this error's presence in the log
- **Normalized pattern** — the deduplicated error text
- **Up to 5 sample lines** — actual raw log lines to aid diagnosis

### Toolbar controls

- **Show Top 5 / Show Top 10** — toggle between 5 or 10 most frequent patterns
- **Copy** — copies the full error list to the clipboard

---

## 8. Tab: Sensors & Probes

### Sensor Refresh Rate Distribution

A vertical bar chart showing **exact sensor counts** from the core.log at the chosen time window: how many sensors are set to each scanning interval (30s, 1min, 5min, 1h, …). Labels are shown in human-readable form. Short intervals on many sensors are the primary driver of high scanning load.

### Sensor Count by Type

A horizontal bar chart showing **exact sensor counts** from the core.log at the chosen time window: the **top 20 sensor types** by raw count (summed across impact levels). Values match the numbers reported in the log for that PRTG core (re)start; no weighting or load calculations.

### Per-probe impact distribution charts

For each of the **top 10 probes**, a bar chart shows sensors at each of the five impact levels. A note indicates how many additional probes exist beyond the top 10.

> **Why impact levels matter:** PRTG processes sensors differently by impact level. A high share of Medium/High/Very High sensors increases CPU and memory usage disproportionately.

### Probes & Sensor Distribution table

| Column | Description |
|---|---|
| Name | Probe display name |
| ID | Internal PRTG probe ID |
| Sensor count | Number of sensors on this probe |
| ERP | Estimated Requests Per second (from log) |

---

## 9. Tab: Timeline

Maps the history of the PRTG Core process over the log's time span.

### Event types

- **[restart]** — a PRTG Core restart, detected via a `Logger initialized` line
- **[milestone]** — a significant startup milestone logged by PRTG

### Timeline scatter chart

Events are plotted on a horizontal time axis with restart events and milestones on separate rows, making it immediately clear whether restarts cluster at a particular period.

> **Interpreting restart density:** More than 10 restarts triggers the Critical finding. More than 5 triggers the Warning. See [Section 13](#13-health-score--rules-engine).

---

## 10. Tab: System Info

A structured key-value view of everything extracted about the host system. All values come *directly* from the log.

| Field | Description |
|---|---|
| OS | Full Windows Server version string |
| CPU count | Number of logical CPU cores |
| CPU model | Processor model name |
| CPU speed | Clock speed in GHz |
| CPU splitting | Whether active, CPUs assigned, split configuration |
| RAM (free / total) | Physical memory in MB |
| Pagefile (free / total) | Page file sizes in MB |
| License owner | Licensed organization name |
| System ID | PRTG internal SystemID |
| Edition & max sensors | License edition and sensor ceiling |
| License days left | Remaining commercial license days |
| Timezone | Server timezone |
| Storage device | Storage device identifier |
| Data path | PRTG data storage path |
| System path | PRTG application installation path |
| Installed / Created / License date | Key installation timestamps |

---

## 11. Timeframe Filter

The **Global Time Window Slider** appears above the tabs after a successful analysis.

### How it works

The analyzer divides the log into **restart segments** (each starting at a `Logger initialized` line). The slider lets you choose how many of the most recent segments to include.

- Drag to **1** → analyze only the current (most recent) restart cycle
- Drag to maximum → analyze the full log (default)
- Restart timestamp markers appear as dots on the slider track

### What changes with the timeframe

- Health score is recomputed for the selected segments
- All findings are re-evaluated
- Error counts (total, last 24h, since restart) are filtered
- Top error patterns reflect the selected window
- System info fields show the configuration as it was at the start of the selected segment

> **Pro tip:** Set the timeframe to the last 1 restart to assess the current state of the instance in isolation, without historical noise.

### Performance

Each timeframe result is **cached in memory in the browser**. Switching between values is instant once computed.

---

## 12. Export

Both export formats respect the currently active timeframe filter.

### JSON Export

Downloads the complete analysis as structured JSON, including:

- All parsed fields (`core` object — server info, sensors, probes, errors, threads, etc.)
- Computed `score` (0–100)
- Full `findings` list with rule IDs, evidence, and recommendations
- `refresh_rate_distribution` array
- `calculated_requests_per_min` value
- `timeline` events
- `metadata` block with analyzer version and file hash

### HTML Report

Downloads a **fully self-contained** standalone HTML file (no internet connection needed to open it), containing:

- Global Snapshot card
- Key Signals card
- Global Impact Distribution donut chart (ECharts, embedded)
- Refresh Rate Distribution bar chart (ECharts, embedded)
- Full Findings & Recommendations list
- Top Errors list

> **License key protection.** The HTML report automatically masks the PRTG license key — only the first 6 and last 4 characters are shown (e.g. `001001…N47D`). Safe to share with customers or attach to tickets.

---

## 13. Health Score & Rules Engine

The health score starts at **100** and has points deducted by each rule that fires. The final score is clamped to 0–100.

| Score range | Verdict |
|---|---|
| ≥ 80 | ✅ **Healthy** |
| 60 – 79 | ⚠️ **Optimization Needed** |
| < 60 | 🔴 **Critical** |

### The 11 Hardcoded Rules

All rules are static, explicit code based on Paessler's published PRTG sizing guidelines. No configurable thresholds, no machine learning.

| Rule ID | Title | Trigger condition | Severity | Score |
|---|---|---|---|---|
| `RULE_1_CPU` | CPU cores below recommended | CPU cores < 95% of required tier | 🔴 Critical | −10 |
| `RULE_2_RAM` | RAM below recommended tier | RAM < 90% of required tier | 🔴 Critical | −10 |
| `RULE_4_OS` | Deprecated Windows Server version | OS year is 2008 or 2012 | 🔴 Critical | −10 |
| `RULE_4_OS` | Aging Windows Server version | OS year is 2016 | ⚠️ Warning | −5 |
| `RULE_7_ERRORS` | Errors detected in Core.log | > 0 operational errors | ⚠️ Warning | −5 |
| `RULE_7_ERRORS` | Many distinct error patterns | > 50 distinct error patterns | 🔴 Critical | −8 |
| `RULE_11_ERP` | High scanning load | Calculated req/min > 15,000 | 🔴 Critical | −10 |
| `RULE_11_ERP` | Elevated scanning load | Calculated req/min > 10,000 | ⚠️ Warning | −6 |
| `RULE_13_DRIVES` | Data and System on same drive | Data drive letter == System drive letter | ⚠️ Warning | −5 |
| `RULE_14_RESTARTS` | High restart frequency | Total restarts > 10 | 🔴 Critical | −5 |
| `RULE_14_RESTARTS` | Elevated restart frequency | Total restarts > 5 | ⚠️ Warning | −3 |
| `RULE_15_THREADS` | Very long-running threads | Max thread runtime > 300 s | 🔴 Critical | −5 |
| `RULE_15_THREADS` | Long-running threads | Max thread runtime > 120 s | ⚠️ Warning | −3 |
| `RULE_16_IMPACT` | High share of medium/high impact sensors | (Medium + High + Very High) / total > 30% | ⚠️ Warning | −4 |
| `RULE_17_CHANNELS` | Many sensors exceed 50 channels | Sensors with > 50 channels > 10 | ⚠️ Warning | −3 |
| `RULE_18_CPU_SPLITTING` | CPU splitting active with > 8 CPUs | CPU splitting enabled AND total CPUs > 8 | ⚠️ Warning | −4 |

### CPU sizing tiers (hardcoded)

| Sensor count | Minimum CPU cores | Tolerance |
|---|---|---|
| < 2,500 | 4 cores | 5% below = rule fires |
| 2,500 – 4,999 | 8 cores | 5% below = rule fires |
| 5,000 – 9,999 | 12 cores | 5% below = rule fires |
| ≥ 10,000 | 16 cores | 5% below = rule fires |

### RAM sizing tiers (hardcoded)

| Sensor count | Minimum RAM | Tolerance |
|---|---|---|
| < 2,500 | 8 GB | 10% below = rule fires |
| 2,500 – 4,999 | 16 GB | 10% below = rule fires |
| 5,000 – 9,999 | 32 GB | 10% below = rule fires |
| ≥ 10,000 | 64 GB | 10% below = rule fires |

### Scanning load calculation

The calculated requests per minute is derived from the sensor interval distribution in the log:

```
requests_per_min += (sensor_count × 60) ÷ interval_seconds
```

Applied to every interval bucket. Independent of the instantaneous ERP value reported in the log.

---

## 14. Reliability & Data Integrity

### 1. Zero AI — fully deterministic

No language models, no machine learning, no probabilistic inference of any kind. The same log file always produces exactly the same result, on any machine, at any time.

### 2. If it's not in the log, it's not shown

Fields that cannot be parsed are left empty or omitted. The analyzer never fills in defaults, never estimates, and never guesses.

### 3. License error exclusion prevents false positives

License activation errors are explicitly filtered out before counting ERRR lines, preventing them from distorting the error picture.

### 4. Deterministic error normalization

Error deduplication replaces variable parts (GUIDs, thread IDs, hex values, long numbers) with fixed tokens via regex substitution. The resulting pattern set is reproducible and auditable.

### 5. Version-keyed cache invalidation

Results are cached on the SHA-256 hash of the file *and* the analyzer version string (`1.5.5`). Upgrading PyPRTG_CLA automatically forces a fresh analysis.

### 6. Comprehensive automated test suite

**38 automated test functions** covering:

- Every data model contract and field type
- Segment assignment and boundary detection
- Error aggregation and pattern deduplication
- Timeframe filtering across multiple segment configurations
- All API endpoints (upload, progress, result, export)
- Cache behavior and version-keyed invalidation
- Status Data parser (HTML and JSON formats from support bundles)
- **Performance budgets:** 5,000 errors processed in < 8 s; 200 restarts handled in < 5 s
- Encoding handling (UTF-8, UTF-16, latin-1)
- Score clamping (always in 0–100)

### 7. Local-only processing

The server binds exclusively to `127.0.0.1`. No data is ever transmitted externally.

---

## 15. Troubleshooting

### Browser cannot reach `http://127.0.0.1:8077`

Confirm the console window is still open and shows the `Uvicorn running on` line. If it closed, relaunch the EXE.

### Port 8077 is already in use

Another instance is using the port. Close all `PyPRTG_CLA.exe` console windows. To use a different port:

```
set PRTG_ANALYZER_PORT=9088
PyPRTG_CLA.exe
```

### Slow first launch (5–15 seconds)

Expected. PyInstaller extracts the Python runtime on first run. Subsequent launches are faster.

### Windows Firewall prompt

Allow local access when prompted. The app only binds to `127.0.0.1` and is never reachable from other machines.

### Windows SmartScreen blocks the EXE

Click **More info** → **Run anyway**. The binary is unsigned. The full source code is in the `source/` folder for inspection.

### Upload fails or analysis produces no results

- Ensure the file is a valid PRTG `Core.log` (not `Probe.log`, `WebServer.log`, etc.)
- Accepted extensions: `.log`, `.gz`, `.txt`
- Very short logs (newly started PRTG) may yield sparse results — this is normal
- Check the console window for server-side error messages

---

## 16. Privacy & Security

| Aspect | Detail |
|---|---|
| **Network binding** | Strictly `127.0.0.1` — unreachable from other machines |
| **Telemetry** | None — no outbound network connections of any kind |
| **License key in exports** | Automatically masked to first 6 + last 4 chars (e.g. `001001…N47D`) |
| **Cache location** | OS temp directory under `prtg_analyzer_cache/` — keyed by SHA-256 hash, deletable at any time |
| **Memory TTL** | Active jobs evicted from server memory after 1 hour |
| **Source code** | Fully included in `source/` for audit, inspection, or rebuild |

---

*PyPRTG_CLA v1.5.5 — PRTG Core Log Analyzer*  
*All analysis is deterministic and based solely on the uploaded `Core.log` file and optional Status Data.*
