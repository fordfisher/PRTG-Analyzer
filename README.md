PyPRTG_CLA v1.5.1
================================

A standalone tool that analyzes PRTG `Core.log` files and presents
an interactive health dashboard in your browser.

Package contents
----------------

```
v1.0f/
├── PyPRTG_CLA.exe                         Main application (self-contained)
├── README.md                              This file
├── manual.html                            Detailed user manual
├── PRTG_Analyzer_Confluence_Blog_Post.md  Blog post for Confluence
└── source/                                Full source code
    ├── app.py                             FastAPI app (upload, caching, exports)
    ├── run_analyzer.py                    Entry point (dev + PyInstaller)
    ├── requirements.txt                   Python dependencies
    ├── PRTG_Analyzerv1.0f.spec            PyInstaller build spec
    ├── analyzer/                          Core analysis package
    │   ├── version.py                     Single source of truth for version
    │   ├── models.py                      Pydantic data models
    │   ├── core_log_parser.py             Streaming Core.log parser
    │   ├── rules_engine.py                Scoring rules engine
    │   ├── analysis.py                    Orchestrator + timeframe filter
    │   ├── erp_calculator.py              Refresh-rate calculation
    │   ├── timeline_analyzer.py           Restart/milestone timeline
    │   ├── report_generator.py            Standalone HTML report
    │   └── status_data_parser.py          Status Data (HTML/JSON) parser
    ├── frontend/                          Browser UI (HTML, CSS, JS, ECharts)
    └── tests/                             Unit + integration tests
```

System requirements
-------------------
- Windows 10 or later (64-bit)
- A modern browser (Edge, Chrome, Firefox)
- Localhost network access (port 8077 must not be blocked)

Starting the analyzer
---------------------
1. Double-click `PyPRTG_CLA.exe`.
2. If Windows SmartScreen warns about an unrecognized app:
   - Click **More info**, then **Run anyway**.
3. Wait a few seconds until the console shows:
   `Uvicorn running on http://127.0.0.1:8077`
4. Open your browser at http://127.0.0.1:8077

First launch may take 5-15 seconds while the app unpacks itself.

Using the web UI
----------------
1. (Optional) Click "Upload Status Data" and select a PRTG Status Data `.htm` file from your support bundle.
2. Drag & drop your PRTG `Core.log` (or `.gz`) onto the upload area.
2. Wait while the log is parsed (live progress is shown).
3. The dashboard appears with (Status Data adds a Now/Historical toggle and Status Snapshot panel when uploaded):
   - Global system information (server, OS, CPU, RAM, license, paths)
   - Health score (0-100) and categorized findings
   - Sensors & probes analysis with impact breakdown
   - Top errors (most frequent non-license error patterns)
   - Timeline of restarts and events
   - Timeframe filter (narrow results to the last N restart cycles)
   - Export options (JSON and standalone HTML report)

Shutting down
-------------
- Close the console window, or press `Ctrl + C` to stop the server.

Troubleshooting
---------------
- **Page does not load** — check the console window is still open and shows
  the "Uvicorn running on" line. Ensure no other process uses port 8077.
- **Slow first launch** — normal; PyInstaller unpacks the runtime on first run.
- **Firewall prompt** — allow local access. The app only binds to 127.0.0.1.
- **SmartScreen warning** — click More info → Run anyway. The binary is
  unsigned; no data leaves your machine.

Development (from source)
-------------------------

1. Open a terminal in the `source/` folder.
2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Run the app:

```bash
python run_analyzer.py
```

4. Run tests:

```bash
python -m pytest tests/ -v
```

5. Build a new EXE:

```bash
pip install pyinstaller
python -m PyInstaller PRTG_Analyzerv1.0f.spec --noconfirm
```

   For releases: name the EXE with the version (e.g. `PyPRTG_CLA_v1.5.1.exe`) to match the auto-update mechanism — set `name='PyPRTG_CLA_v1.5.1'` in the spec or rename the output.

Notes
-----
- Input is a single `Core.log` file (optionally `.gz` compressed).
- Large logs are streamed — never fully loaded into memory.
- Results are cached by SHA-256; re-analysing the same log is instant.
- The app only binds to `127.0.0.1` — no data leaves the machine.
- Port defaults to `8077`; set `PRTG_ANALYZER_PORT` env var to override.
