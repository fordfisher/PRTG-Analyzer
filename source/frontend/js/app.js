import { ChartManager } from "./charts.js?v=1.4";
import {
  renderErrors,
  renderFindings,
  renderHealth,
  renderMetrics,
  renderNowToggle,
  renderSensorsTable,
  renderStatusSnapshot,
  renderSummary,
  renderSystemInfo,
  renderTimelineList,
  renderTimeframeSelector,
} from "./renderers.js?v=1.4";
import { getState, resetResultState, updateState } from "./state.js?v=1.4";
import { debounce } from "./utils.js?v=1.4";
import { buildViewModel } from "./view-model.js?v=1.4";

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const statusDataZone = document.getElementById("status-data-zone");
const statusDataInput = document.getElementById("status-data-input");
const statusDataLabel = document.getElementById("status-data-label");
const progressBar = document.querySelector("#progress .bar");
const statusText = document.getElementById("status-text");
const dashboard = document.getElementById("dashboard");
const tabs = document.querySelectorAll(".tabs button");
const tabContents = document.querySelectorAll(".tab-content");
const chartManager = new ChartManager();

const elements = {
  viewToggle: document.getElementById("view-toggle-wrap"),
  timeframeWrap: document.getElementById("global-timeframe-wrap"),
  summary: document.getElementById("overview-summary"),
  statusSnapshot: document.getElementById("overview-status-snapshot"),
  health: document.getElementById("overview-health"),
  metrics: document.getElementById("overview-metrics"),
  findings: document.getElementById("findings-list"),
  errorsToolbar: document.getElementById("errors-toolbar"),
  errorsList: document.getElementById("errors-list"),
  system: document.getElementById("system-info"),
  sensorsTable: document.getElementById("sensors-table"),
  timelineList: document.getElementById("timeline-list"),
};

function setStatus(text) {
  if (statusText) statusText.textContent = text;
}

function setProgress(ratio) {
  if (!progressBar) return;
  const clamped = Math.max(0, Math.min(1, ratio));
  progressBar.style.width = `${clamped * 100}%`;
}

function buildCurrentViewModel() {
  const state = getState();
  return state.lastResult ? buildViewModel(state.lastResult, state) : null;
}

function renderApp(result) {
  const state = getState();
  updateState({ lastResult: result });
  const vm = buildViewModel(result, state);

  renderNowToggle(elements.viewToggle, vm, state, handleViewToggle);
  renderTimeframeSelector(elements.timeframeWrap, vm, state, setGlobalTimeFrame);
  renderSummary(elements.summary, vm);
  renderStatusSnapshot(elements.statusSnapshot, vm, state);
  renderHealth(elements.health, vm);
  renderMetrics(elements.metrics, vm);
  renderFindings(elements.findings, vm, state);
  renderErrors(elements.errorsToolbar, elements.errorsList, vm, state, (count) => {
    updateState({ showTopErrorsCount: count });
    renderApp(getState().lastResult);
  });
  renderSystemInfo(elements.system, vm);
  renderSensorsTable(elements.sensorsTable, vm);
  renderTimelineList(elements.timelineList, vm);
  chartManager.renderTab(state.activeTab, vm);
  syncChartExportCheckboxes();
}

function syncChartExportCheckboxes() {
  const state = getState();
  const selected = new Set(state.exportSelectedCharts || []);
  const checkboxes = document.querySelectorAll(".chart-export-checkbox");
  checkboxes.forEach((input) => {
    const id = input.getAttribute("data-export-chart-id");
    if (!id) return;
    input.checked = selected.has(id);
    if (!input.dataset.bound) {
      input.dataset.bound = "1";
      input.addEventListener("change", () => {
        const current = getState().exportSelectedCharts || [];
        const next = input.checked
          ? (current.includes(id) ? current : [...current, id])
          : current.filter((c) => c !== id);
        updateState({ exportSelectedCharts: next });
      });
    }
  });
  document.querySelectorAll(".finding-export-checkbox").forEach((input) => {
    const idx = input.getAttribute("data-export-finding-index");
    if (idx === null) return;
    const index = parseInt(idx, 10);
    if (Number.isNaN(index)) return;
    const selected = Array.isArray(state.exportSelectedFindings) ? state.exportSelectedFindings : [];
    input.checked = selected.includes(index);
    if (!input.dataset.bound) {
      input.dataset.bound = "1";
      input.addEventListener("change", () => {
        const current = getState().exportSelectedFindings || [];
        const next = input.checked
          ? (current.includes(index) ? current : [...current, index].sort((a, b) => a - b))
          : current.filter((i) => i !== index);
        updateState({ exportSelectedFindings: next });
      });
    }
  });
  const addAllBtn = document.querySelector(".probe-add-all-btn");
  if (addAllBtn && !addAllBtn.dataset.bound) {
    addAllBtn.dataset.bound = "1";
    addAllBtn.addEventListener("click", () => {
      const inputs = document.querySelectorAll('.chart-export-checkbox[data-export-chart-id^="probe-impact-"]');
      const ids = Array.from(inputs).map((el) => el.getAttribute("data-export-chart-id")).filter(Boolean);
      const current = getState().exportSelectedCharts || [];
      const next = [...new Set([...current, ...ids])];
      updateState({ exportSelectedCharts: next });
      syncChartExportCheckboxes();
    });
  }
}

function handleViewToggle(timeframe) {
  updateState({ globalTimeFrame: timeframe });
  const state = getState();
  if (state.lastFullResult) {
    updateState({ lastResult: state.lastFullResult });
    renderApp(state.lastFullResult);
  }
}

async function setGlobalTimeFrame(timeframe) {
  const state = getState();
  updateState({ globalTimeFrame: timeframe });
  const rangeInput = elements.timeframeWrap?.querySelector("input[type=range]");
  if (rangeInput) rangeInput.disabled = true;
  try {
    if (timeframe === "now") {
      if (state.lastFullResult) {
        updateState({ lastResult: state.lastFullResult });
        renderApp(state.lastFullResult);
      }
      return;
    }
    if (timeframe === "all") {
      if (state.lastFullResult) {
        updateState({ lastResult: state.lastFullResult });
        renderApp(state.lastFullResult);
      }
      return;
    }
    if (!state.lastHash) return;

    const cached = state.timeframeResults.get(timeframe);
    if (cached) {
      updateState({ lastResult: cached });
      renderApp(cached);
      return;
    }

    const response = await fetch(`/api/result/${state.lastHash}?timeframe=${encodeURIComponent(timeframe)}`);
    if (!response.ok) return;
    const data = await response.json();
    state.timeframeResults.set(timeframe, data);
    updateState({ lastResult: data });
    renderApp(data);
  } finally {
    if (rangeInput) rangeInput.disabled = false;
  }
}

function switchTab(id) {
  updateState({ activeTab: id });
  tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === id));
  tabContents.forEach((section) => section.classList.toggle("active", section.id === `tab-${id}`));

  const vm = buildCurrentViewModel();
  if (vm) {
    chartManager.renderTab(id, vm);
    chartManager.resizeVisible();
  }
}

async function uploadViaFetch(file) {
  const formData = new FormData();
  formData.append("core_log", file);
  const statusFile = statusDataInput?.files?.[0];
  if (statusFile) {
    formData.append("status_data", statusFile);
  }
  setStatus(statusFile ? "Uploading Core.log + Status Data..." : "Uploading Core.log...");
  setProgress(0.15);

  const response = await fetch("/api/analyze", { method: "POST", body: formData });
  if (!response.ok) {
    setStatus(`Error: ${response.status} ${response.statusText}`);
    return;
  }

  const payload = await response.json();
  const jobId = payload.job_id;
  updateState({ lastHash: payload.hash || null });
  setProgress(0.35);
  setStatus("Queued for analysis...");
  if (!jobId) {
    setStatus("Error: missing job id from server.");
    return;
  }

  const eventSource = new EventSource(`/api/progress/${jobId}`);
  eventSource.onmessage = async (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.status === "queued") {
        setStatus("Queued...");
        setProgress(0.4);
      } else if (message.status === "analyzing") {
        setStatus("Analyzing...");
        setProgress(0.65);
      } else if (message.status === "done") {
        eventSource.close();
        setStatus("Finalizing...");
        setProgress(0.9);
        const { lastHash } = getState();
        if (!lastHash) {
          setStatus("Error: missing result hash.");
          return;
        }
        const resultResponse = await fetch(`/api/result/${lastHash}`);
        if (!resultResponse.ok) {
          setStatus("Error: failed to load analysis result.");
          return;
        }
        const result = await resultResponse.json();
        resetResultState(result, lastHash);
        setProgress(1);
        setStatus("Analysis complete.");
        if (dashboard) {
          dashboard.hidden = false;
          requestAnimationFrame(() => dashboard.classList.add("dashboard-visible"));
        }
        renderApp(result);
      } else if (message.status === "error") {
        eventSource.close();
        setStatus(`Analysis failed: ${message.error || "unknown error"}`);
        setProgress(0);
      }
    } catch (error) {
      console.error(error);
    }
  };
  eventSource.addEventListener("end", () => eventSource.close());
}

function attachExportButtons() {
  const btnJson = document.getElementById("btn-download-json");
  const btnHtml = document.getElementById("btn-download-html");
  function buildExportSuffix(state, forHtml = false) {
    const params = new URLSearchParams();
    if (state.globalTimeFrame && state.globalTimeFrame !== "all") {
      params.set("timeframe", state.globalTimeFrame);
    }
    const patterns = Array.isArray(state.exportSelectedErrorPatterns) ? state.exportSelectedErrorPatterns : [];
    if (patterns.length) {
      params.set("errors_patterns", patterns.join(","));
    }
    if (forHtml) {
      const charts = Array.isArray(state.exportSelectedCharts) ? state.exportSelectedCharts : [];
      params.set("charts", charts.join(","));
      const findingIndices = Array.isArray(state.exportSelectedFindings) ? state.exportSelectedFindings : [];
      params.set("findings", findingIndices.join(","));
    }
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }
  if (btnJson) {
    btnJson.onclick = () => {
      const state = getState();
      if (!state.lastHash) return;
      const suffix = buildExportSuffix(state);
      window.open(`/api/export/json/${state.lastHash}${suffix}`, "_blank");
    };
  }
  if (btnHtml) {
    btnHtml.onclick = () => {
      const state = getState();
      if (!state.lastHash) return;
      const suffix = buildExportSuffix(state, true);
      window.open(`/api/export/html/${state.lastHash}${suffix}`, "_blank");
    };
  }
}

tabs.forEach((button) => {
  button.addEventListener("click", () => {
    const id = button.dataset.tab;
    if (id) switchTab(id);
  });
});

dropZone?.addEventListener("click", (event) => {
  if (event.target === fileInput) return;
  fileInput?.click();
});
dropZone?.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("hover");
});
dropZone?.addEventListener("dragleave", (event) => {
  event.preventDefault();
  if (!dropZone.contains(event.relatedTarget)) dropZone.classList.remove("hover");
});
dropZone?.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("hover");
  const files = event.dataTransfer?.files;
  if (files?.length) {
    uploadViaFetch(files[0]).catch((error) => {
      console.error(error);
      setStatus("Unexpected error during upload.");
    });
  }
});

fileInput?.addEventListener("change", () => {
  const files = fileInput.files;
  if (files?.length) {
    uploadViaFetch(files[0]).catch((error) => {
      console.error(error);
      setStatus("Unexpected error during upload.");
    });
  }
});

statusDataZone?.addEventListener("click", (event) => {
  if (event.target === statusDataInput) return;
  statusDataInput?.click();
});
statusDataInput?.addEventListener("change", () => {
  const hasFile = statusDataInput.files?.length > 0;
  statusDataZone?.classList.toggle("has-file", hasFile);
  if (statusDataLabel) {
    statusDataLabel.textContent = hasFile ? statusDataInput.files[0].name : "Upload Status Data";
  }
});

window.addEventListener("resize", debounce(() => chartManager.resizeVisible(), 120));
attachExportButtons();

// ---------------------------------------------------------------------------
// Auto-update
// ---------------------------------------------------------------------------

function showUpdateStatus(message, clearAfterMs = 4000) {
  const el = document.getElementById("update-status");
  if (!el) return;
  el.textContent = message;
  if (clearAfterMs > 0) setTimeout(() => { el.textContent = ""; }, clearAfterMs);
}

async function checkForUpdate(userInitiated = false) {
  try {
    const resp = await fetch("/api/update-check");
    if (!resp.ok) return;
    const info = await resp.json();

    if (info.error) {
      if (userInitiated) showUpdateStatus("Update check failed (network or server)", 6000);
      return;
    }
    if (info.up_to_date) {
      if (userInitiated) showUpdateStatus("Up to date", 4000);
      return;
    }

    const overlay = document.getElementById("update-overlay");
    const overlayTitle = document.getElementById("update-overlay-title");
    const overlayMessage = document.getElementById("update-overlay-message");
    const overlayActions = document.getElementById("update-overlay-actions");
    const overlayBtn = document.getElementById("update-overlay-btn");
    const overlayDismiss = document.getElementById("update-overlay-dismiss");
    if (!overlay || !overlayMessage || !overlayBtn) return;

    document.getElementById("update-status").textContent = "";
    overlayTitle.textContent = "Update available";
    overlayMessage.textContent = `Version ${info.latest} is ready. Update now to get the latest version.`;
    overlayActions.hidden = false;
    overlayBtn.hidden = false;
    overlayBtn.disabled = false;
    overlayBtn.textContent = "Update now";
    overlay.hidden = false;

    overlayDismiss?.addEventListener("click", () => {
      overlay.hidden = true;
    }, { once: true });

    overlayBtn.addEventListener("click", async () => {
      overlayBtn.disabled = true;
      overlayMessage.textContent = "Downloading update…";
      overlayActions.hidden = true;
      try {
        const r = await fetch("/api/apply-update", { method: "POST" });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          overlayMessage.textContent = `Update failed: ${err.detail || r.statusText}`;
          overlayActions.hidden = false;
          overlayBtn.hidden = false;
          overlayBtn.disabled = false;
          overlayBtn.textContent = "Retry";
          return;
        }
        overlayMessage.textContent = "Restarting… The app will close and reopen in a moment.";
        overlayTitle.textContent = "Almost done";
        const reloadBtn = document.createElement("button");
        reloadBtn.type = "button";
        reloadBtn.className = "update-overlay-btn";
        reloadBtn.textContent = "Reload page";
        reloadBtn.style.marginTop = "1rem";
        reloadBtn.onclick = () => window.location.reload();
        overlayActions.hidden = false;
        overlayActions.appendChild(reloadBtn);
        (function waitForNewApp() {
          const maxWait = 30000;
          const start = Date.now();
          function poll() {
            const ctrl = new AbortController();
            const t = setTimeout(() => ctrl.abort(), 3000);
            fetch("/api/update-check", { method: "GET", signal: ctrl.signal })
              .then(() => { clearTimeout(t); window.location.reload(); })
              .catch(() => {
                clearTimeout(t);
                if (Date.now() - start < maxWait) setTimeout(poll, 2000);
              });
          }
          setTimeout(poll, 6000);
        })();
      } catch (e) {
        overlayMessage.textContent = `Update error: ${e.message}`;
        overlayActions.hidden = false;
        overlayBtn.hidden = false;
        overlayBtn.disabled = false;
        overlayBtn.textContent = "Retry";
      }
    }, { once: true });
  } catch {
    // silently ignore — not critical
  }
}

checkForUpdate();
document.getElementById("check-updates-btn")?.addEventListener("click", () => checkForUpdate(true));

