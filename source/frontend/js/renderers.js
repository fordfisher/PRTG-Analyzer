import { escapeHtml, setHtmlIfChanged } from "./utils.js?v=1.3";

export function renderTimeframeSelector(element, vm, state, onChange) {
  if (!element) return;
  const { sliderModel } = vm;
  if (!sliderModel || !sliderModel.max || state.globalTimeFrame === "now") {
    setHtmlIfChanged(element, "");
    return;
  }

  const { markers, max } = sliderModel;
  const currentValue = state.globalTimeFrame === "now" ? "all" : (state.globalTimeFrame || "all");
  const numericValue = currentValue === "all" ? max : Math.min(parseInt(currentValue, 10) || max, max);

  const markerDots = markers
    .map(
      (m) =>
        `<span class="slider-marker" style="left:${m.pct.toFixed(2)}%" data-tip="${escapeHtml(m.label + " \u2014 " + m.formatted)}"></span>`
    )
    .join("");

  function labelForValue(val) {
    if (val >= max) return "All";
    return `Past ${val} restart${val > 1 ? "s" : ""}`;
  }

  setHtmlIfChanged(
    element,
    `<div class="timeframe-slider-wrap">
       <label class="global-timeframe-label">Time Window: <span class="slider-value-label">${escapeHtml(labelForValue(numericValue))}</span></label>
       <div class="slider-track-wrap">
         <input type="range" id="global-timeframe-range" class="timeframe-range" min="1" max="${max}" value="${numericValue}" step="1" />
         <div class="slider-markers">${markerDots}</div>
       </div>
     </div>`
  );

  const range = element.querySelector("#global-timeframe-range");
  if (!range) return;
  range.oninput = (e) => {
    const val = parseInt(e.target.value, 10);
    const lbl = element.querySelector(".slider-value-label");
    if (lbl) lbl.textContent = labelForValue(val);
  };
  range.onchange = (e) => {
    const val = parseInt(e.target.value, 10);
    onChange(val >= max ? "all" : String(val));
  };
}

export function renderSummary(element, vm) {
  if (!element) return;
  const { core, result } = vm;
  const totalCpus = core.cpu_total_for_splitting ?? core.cpu_count ?? 0;
  const assignedCpus = core.cpu_assigned ?? totalCpus;
  const splittingActive = core.cpu_splitting_active === true;
  const cpuLine = splittingActive
    ? `CPU splitting: <b>Active</b> (${escapeHtml(String(assignedCpus))} of ${escapeHtml(String(totalCpus))} cores used)`
    : totalCpus > 0
    ? `CPU splitting: <b>Inactive</b> (all ${escapeHtml(String(totalCpus))} cores used)`
    : "CPU splitting: not detected";

  setHtmlIfChanged(
    element,
    `<div class="section-stack">
      <div class="section-title">Global Snapshot</div>
      <div>Server: <b>${escapeHtml(core.server_name || "Unknown")}</b> - PRTG <b>${escapeHtml(core.prtg_version || "")}</b></div>
      <div>License owner: <b>${escapeHtml(core.license_owner || "—")}</b></div>
      <div>SystemID: <span class="mono-text">${escapeHtml(core.system_id || "—")}</span></div>
      <div>Sensors: <b>${escapeHtml(core.total_sensors ?? "")}</b> - Probes: <b>${escapeHtml(core.total_probes ?? core.probes?.length ?? "")}</b></div>
      <div>Estimated RPS: <b>${escapeHtml(core.estimated_requests_per_second ?? "")}</b> - Score: <b>${escapeHtml(result.score ?? "")}</b></div>
      <div>${cpuLine}</div>
    </div>`
  );
}

export function renderHealth(element, vm) {
  if (!element) return;
  const { core, result } = vm;
  const score = Number(result.score ?? 0);
  let label = "Healthy";
  let color = "#22c55e";
  if (score < 60) {
    label = "Critical";
    color = "#ef4444";
  } else if (score < 80) {
    label = "Optimization Needed";
    color = "#eab308";
  }

  const pills = [];
  if (core.total_restarts > 0) {
    pills.push(`<span class="status-pill">Restarts: ${escapeHtml(String(core.total_restarts))}</span>`);
  }
  if ((core.total_errors || 0) > 0 || (core.total_warnings || 0) > 0) {
    pills.push(
      `<span class="status-pill status-pill-error">Errors: ${escapeHtml(String(core.total_errors ?? 0))}, Warnings: ${escapeHtml(
        String(core.total_warnings ?? 0)
      )}</span>`
    );
  }

  setHtmlIfChanged(
    element,
    `<div class="split-row">
      <div>
        <div class="section-kicker">Instance Health</div>
        <div class="health-score" style="color:${color}">${escapeHtml(label)} <span>(${escapeHtml(String(score))}/100)</span></div>
        <div class="muted-text">Log span: ${escapeHtml(String(core.log_span_days?.toFixed?.(1) ?? core.log_span_days ?? ""))} days · Restarts: ${escapeHtml(
          String(core.total_restarts ?? 0)
        )}</div>
      </div>
      <div class="pill-row">${pills.join("")}</div>
    </div>`
  );
}

export function renderMetrics(element, vm) {
  if (!element) return;
  const { core, result, busiestProbe } = vm;
  const rpm = Number(result.calculated_requests_per_min ?? 0);
  const errorTotal = Number(core.total_errors ?? 0);
  const errors24h = Number(core.errors_last_24h ?? 0);
  const errorsSinceRestart = Number(core.errors_since_last_restart ?? 0);

  const html = `
    <div class="metric-grid">
      <div class="metric-card">
        <div class="section-kicker">Load & ERP</div>
        <div class="metric-value">${escapeHtml(rpm.toFixed(0))} req/min</div>
        <div class="muted-text">Total ERP (log): ${escapeHtml(String(core.total_erp ?? 0))}</div>
        <div class="muted-text">${busiestProbe ? `Busiest probe: ${escapeHtml(busiestProbe.name || "")} (${escapeHtml(String(busiestProbe.erp ?? "—"))} ERP)` : "No ERP data per probe"}</div>
      </div>
      <div class="metric-card">
        <div class="section-kicker">Stability</div>
        <div class="metric-value">${escapeHtml(String(core.total_restarts ?? 0))} restarts</div>
        <div class="muted-text">Warnings: ${escapeHtml(String(core.total_warnings ?? 0))}</div>
      </div>
      <div class="metric-card">
        <div class="section-kicker">License & OS</div>
        <div class="metric-value">${escapeHtml(core.license_owner || "—")}</div>
        <div class="muted-text">${escapeHtml(core.os_version || "Unknown OS")}</div>
      </div>
      <div class="metric-card">
        <div class="section-kicker">Errors</div>
        <div class="metric-value">${escapeHtml(String(errorTotal))}</div>
        <div class="muted-text">Last 24h: ${escapeHtml(String(errors24h))}</div>
        <div class="muted-text">Since restart: ${escapeHtml(String(errorsSinceRestart))}</div>
      </div>
    </div>
  `;
  setHtmlIfChanged(element, html);
}

export function renderFindings(element, vm) {
  if (!element) return;
  const cards = (vm.result.findings || [])
    .map((finding) => {
      const sev = String(finding.severity || "info").toLowerCase();
      const color = sev === "red" ? "#ff4d6d" : sev === "yellow" ? "#ffd166" : sev === "green" ? "#00ff9c" : "#7df9ff";
      const evidence = (finding.evidence || [])
        .map((item) => `<div class="muted-text"><small>${escapeHtml(item.label)}:</small> ${escapeHtml(item.value)}</div>`)
        .join("");
      return `<div class="finding-card">
        <div class="split-row">
          <div style="font-weight:700;color:${color}">${escapeHtml(finding.title)}</div>
          <div class="muted-text"><small>${escapeHtml(finding.rule_id)} · ${escapeHtml(finding.score_delta)}</small></div>
        </div>
        <div class="finding-rec">${escapeHtml(finding.recommendation)}</div>
        <div class="section-stack compact-gap">${evidence}</div>
      </div>`;
    })
    .join("");

  setHtmlIfChanged(element, `<div class="section-stack">${cards || "<div>No findings.</div>"}</div>`);
}

export function renderErrors(toolbarElement, listElement, vm, state, onCountChange) {
  if (!toolbarElement || !listElement) return;
  setHtmlIfChanged(
    toolbarElement,
    `<div class="errors-toolbar-label">Show</div>
     <button type="button" id="errors-btn-5" class="errors-toggle-btn">Top 5</button>
     <button type="button" id="errors-btn-10" class="errors-toggle-btn">Top 10</button>
     <span id="errors-count-label" class="errors-count-label">${escapeHtml(vm.errorCountLabel)}</span>
     <button type="button" id="errors-copy-btn" class="errors-copy-btn">Copy</button>`
  );

  const cards = vm.visibleErrors
    .map((entry) => {
      const samples = (entry.sample_lines || [])
        .map((line) => `<div class="mono-block">${escapeHtml(line)}</div>`)
        .join("");
      return `<div class="error-card">
        <div class="split-row">
          <div style="font-weight:700;color:#ff4d6d">#${escapeHtml(entry.rank)} · ${escapeHtml(entry.count)}x</div>
          <div class="muted-text"><small>${escapeHtml(entry.first_seen)} -> ${escapeHtml(entry.last_seen)}</small></div>
        </div>
        <div>${escapeHtml(entry.pattern)}</div>
        <div class="section-stack compact-gap">${samples}</div>
      </div>`;
    })
    .join("");

  setHtmlIfChanged(listElement, `<div class="section-stack">${cards || "<div>No errors in this time frame.</div>"}</div>`);

  const buttonFive = toolbarElement.querySelector("#errors-btn-5");
  const buttonTen = toolbarElement.querySelector("#errors-btn-10");
  const label = toolbarElement.querySelector("#errors-count-label");
  const copyButton = toolbarElement.querySelector("#errors-copy-btn");

  if (buttonFive) {
    buttonFive.classList.toggle("active", state.showTopErrorsCount === 5);
    buttonFive.onclick = () => onCountChange(5);
  }
  if (buttonTen) {
    buttonTen.classList.toggle("active", state.showTopErrorsCount === 10);
    buttonTen.onclick = () => onCountChange(10);
  }
  if (label) {
    label.textContent = vm.errorCountLabel;
  }
  if (copyButton) {
    copyButton.onclick = async () => {
      const text = vm.visibleErrors.length
        ? vm.visibleErrors
            .map((entry) => `#${entry.rank} · ${entry.count}x (${entry.first_seen} -> ${entry.last_seen})\n${entry.pattern}`)
            .join("\n\n")
        : "No errors.";
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        copyButton.textContent = "Copied!";
        window.setTimeout(() => {
          copyButton.textContent = "Copy";
        }, 1200);
      }
    };
  }
}

export function renderSystemInfo(element, vm) {
  if (!element) return;
  const { core } = vm;
  const rows = [
    ["OS", core.os_version],
    ["CPU", `${core.cpu_count || ""} ${core.cpu_model || ""}`.trim()],
    ["RAM (MB)", `${core.free_ram_mb || ""} free / ${core.total_ram_mb || ""} total`.trim()],
    ["Pagefile (MB)", `${core.free_pagefile_mb || ""} free / ${core.total_pagefile_mb || ""} total`.trim()],
    ["License owner", core.license_owner || "—"],
    ["SystemID", core.system_id || "—"],
    ["Timezone", core.timezone],
    ["Storage", core.storage_device],
    ["Data path", core.data_path],
    ["System path", core.system_path],
  ];

  setHtmlIfChanged(
    element,
    `<div class="section-title">System Info</div>
     <div class="section-stack">
       ${rows
         .map(
           ([label, value]) =>
             `<div class="kv-row"><div class="kv-key">${escapeHtml(label)}</div><div>${escapeHtml(value ?? "")}</div></div>`
         )
         .join("")}
     </div>`
  );
}

export function renderSensorsTable(element, vm) {
  if (!element) return;
  const rows = vm.probesBySensorCount
    .map((probe) => {
      const erp = probe.erp != null ? Number(probe.erp).toFixed(3) : "—";
      return `<div class="probe-row">
        <div>
          <div style="font-weight:600;color:#e4f0ff">${escapeHtml(probe.name || "")}</div>
          <div class="muted-text">${probe.probe_id != null ? `#${escapeHtml(probe.probe_id)}` : ""}</div>
        </div>
        <div class="mono-text">${escapeHtml(probe.sensor_count || 0)}</div>
        <div class="mono-text">${escapeHtml(erp)}</div>
      </div>`;
    })
    .join("");

  setHtmlIfChanged(
    element,
    `<div class="section-title">Probes & Sensor Distribution</div>
     ${
       rows
         ? `<div class="probe-header"><div>Probe</div><div class="mono-text">Sensors</div><div class="mono-text">ERP</div></div>
            <div class="section-stack compact-gap">${rows}</div>`
         : `<div class="muted-text">No probes were parsed from this Core.log.</div>`
     }`
  );
}

export function renderTimelineList(element, vm) {
  if (!element) return;
  const items = vm.timelinePoints
    .map(
      (point) =>
        `<div class="timeline-row"><div class="timeline-time">${escapeHtml(point.timestamp || "")}</div><div>[${escapeHtml(
          point.kind || ""
        )}] ${escapeHtml(point.label || "")}</div></div>`
    )
    .join("");

  setHtmlIfChanged(
    element,
    `<div class="section-title">Timeline Events</div>
     ${
       items
         ? `<div class="section-stack compact-gap timeline-list">${items}</div>`
         : '<div class="muted-text">No restarts or startup milestones were detected in this Core.log.</div>'
     }`
  );
}

export function renderNowToggle(element, vm, state, onToggle) {
  if (!element) return;
  if (!vm.hasStatusSnapshot) {
    setHtmlIfChanged(element, "");
    return;
  }
  const isNow = state.globalTimeFrame === "now";
  setHtmlIfChanged(
    element,
    `<span class="view-toggle-label">View:</span>
     <div class="view-toggle-group">
       <button type="button" class="view-toggle-btn${isNow ? " active" : ""}" data-view="now">Now</button>
       <button type="button" class="view-toggle-btn${!isNow ? " active" : ""}" data-view="historical">Historical</button>
     </div>`
  );
  element.querySelectorAll(".view-toggle-btn").forEach((btn) => {
    btn.onclick = () => onToggle(btn.dataset.view === "now" ? "now" : "all");
  });
}

function _deltaHtml(current, previous, unit) {
  if (current == null || previous == null) return "";
  const diff = current - previous;
  if (diff === 0) return ` <span class="muted-text">(unchanged from last boot)</span>`;
  const sign = diff > 0 ? "+" : "";
  const color = diff > 0 ? "#eab308" : "#22c55e";
  const suffix = unit ? ` ${unit}` : "";
  return ` <span style="color:${color}">(${sign}${diff}${suffix} vs last boot)</span>`;
}

export function renderStatusSnapshot(element, vm, state) {
  if (!element) return;
  const snap = vm.statusSnapshot;
  const showSnapshot = snap && (state.globalTimeFrame === "now" || state.globalTimeFrame === "all");

  if (!showSnapshot) {
    setHtmlIfChanged(element, "");
    element.style.display = "none";
    return;
  }
  element.style.display = "";

  const boot = vm.lastBootSnapshot || {};
  const bootSensors = boot.total_sensors ?? vm.core.total_sensors ?? null;
  const isJson = snap.source_format === "json";

  const metricCards = [];
  metricCards.push(`<div class="metric-card">
    <div class="section-kicker">Total Sensors</div>
    <div class="metric-value">${escapeHtml(String(snap.total_sensors ?? "—"))}</div>
    <div class="muted-text">${_deltaHtml(snap.total_sensors, bootSensors, "")}</div>
  </div>`);

  if (isJson) {
    metricCards.push(`<div class="metric-card">
      <div class="section-kicker">Up</div>
      <div class="metric-value" style="color:#22c55e">${escapeHtml(String(snap.sensors_up ?? "—"))}</div>
    </div>`);
    metricCards.push(`<div class="metric-card">
      <div class="section-kicker">Warning</div>
      <div class="metric-value" style="color:#eab308">${escapeHtml(String(snap.sensors_warning ?? "—"))}</div>
    </div>`);
    metricCards.push(`<div class="metric-card">
      <div class="section-kicker">Down / Alarm</div>
      <div class="metric-value" style="color:#ef4444">${escapeHtml(String(snap.sensors_down ?? "—"))}</div>
    </div>`);
  } else {
    if (snap.server_cpu_load_pct != null) {
      metricCards.push(`<div class="metric-card">
        <div class="section-kicker">Server CPU Load</div>
        <div class="metric-value">${escapeHtml(String(snap.server_cpu_load_pct))}%</div>
      </div>`);
    }
    if (snap.requests_per_second != null) {
      metricCards.push(`<div class="metric-card">
        <div class="section-kicker">Requests/Second</div>
        <div class="metric-value">${escapeHtml(String(snap.requests_per_second))}</div>
      </div>`);
    }
    if (snap.slow_request_ratio_pct != null) {
      metricCards.push(`<div class="metric-card">
        <div class="section-kicker">Slow Request Ratio</div>
        <div class="metric-value">${escapeHtml(String(snap.slow_request_ratio_pct))}%</div>
      </div>`);
    }
  }

  let detailSection = "";
  if (isJson) {
    const statusRows = [
      ["Paused", snap.sensors_paused],
      ["Unknown", snap.sensors_unknown],
    ].filter(([, v]) => v != null && v > 0)
      .map(([label, val]) => `<div class="kv-row"><div class="kv-key">${escapeHtml(label)}</div><div>${escapeHtml(String(val))}</div></div>`)
      .join("");
    if (statusRows) {
      detailSection = `<div class="section-title" style="margin-top:12px">Other Status</div>
        <div class="section-stack compact-gap">${statusRows}</div>`;
    }
    if (snap.prtg_version) {
      detailSection += `<div class="muted-text" style="margin-top:8px">PRTG Version: ${escapeHtml(snap.prtg_version)}</div>`;
    }
  } else {
    const impactLevels = ["Very low", "Low", "Medium", "High", "Very high"];
    const impactRows = impactLevels.map((level) => {
      const nowCount = snap.impact_distribution?.[level]?.total ?? 0;
      const bootImpact = boot.global_impact_distribution?.[level] ?? vm.core.global_impact_distribution?.[level];
      const bootCount = bootImpact?.total ?? null;
      return `<div class="kv-row">
        <div class="kv-key">${escapeHtml(level)}</div>
        <div>${escapeHtml(String(nowCount))} sensors${_deltaHtml(nowCount, bootCount, "")}</div>
      </div>`;
    }).join("");
    detailSection = `<div class="section-title" style="margin-top:12px">Sensor Impact (from bundle)</div>
      <div class="section-stack compact-gap">${impactRows}</div>`;
  }

  const html = `<div class="section-stack">
    <div class="section-title">Status Snapshot (from bundle)</div>
    <div class="metric-grid">${metricCards.join("")}</div>
    ${detailSection}
  </div>`;

  setHtmlIfChanged(element, html);
}
