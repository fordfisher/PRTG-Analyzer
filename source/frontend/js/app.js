import { ChartManager } from "./charts.js?v=1.3";
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
} from "./renderers.js?v=1.3";
import { getState, resetResultState, updateState } from "./state.js?v=1.3";
import { debounce } from "./utils.js?v=1.3";
import { buildViewModel } from "./view-model.js?v=1.3";

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
  renderFindings(elements.findings, vm);
  renderErrors(elements.errorsToolbar, elements.errorsList, vm, state, (count) => {
    updateState({ showTopErrorsCount: count });
    renderApp(getState().lastResult);
  });
  renderSystemInfo(elements.system, vm);
  renderSensorsTable(elements.sensorsTable, vm);
  renderTimelineList(elements.timelineList, vm);
  chartManager.renderTab(state.activeTab, vm);
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
  console.log("[DEBUG] statusDataInput element:", statusDataInput);
  console.log("[DEBUG] statusDataInput.files:", statusDataInput?.files);
  console.log("[DEBUG] statusFile:", statusFile);
  if (statusFile) {
    formData.append("status_data", statusFile);
    console.log("[DEBUG] Appended status_data to FormData:", statusFile.name, statusFile.size, "bytes");
  } else {
    console.log("[DEBUG] No status file selected — uploading Core.log only");
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
        console.log("[DEBUG] Result has status_snapshot:", !!result?.status_snapshot);
        if (result?.status_snapshot) {
          console.log("[DEBUG] status_snapshot keys:", Object.keys(result.status_snapshot));
          console.log("[DEBUG] status_snapshot:", JSON.stringify(result.status_snapshot).slice(0, 300));
        }
        resetResultState(result, lastHash);
        setProgress(1);
        setStatus(result?.status_snapshot ? "Analysis complete. Status data included." : "Analysis complete.");
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
  if (btnJson) {
    btnJson.onclick = () => {
      const state = getState();
      if (!state.lastHash) return;
      const suffix = state.globalTimeFrame === "all" ? "" : `?timeframe=${encodeURIComponent(state.globalTimeFrame)}`;
      window.open(`/api/export/json/${state.lastHash}${suffix}`, "_blank");
    };
  }
  if (btnHtml) {
    btnHtml.onclick = () => {
      const state = getState();
      if (!state.lastHash) return;
      const suffix = state.globalTimeFrame === "all" ? "" : `?timeframe=${encodeURIComponent(state.globalTimeFrame)}`;
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
  console.log("[DEBUG] Status data file changed. hasFile:", hasFile, hasFile ? statusDataInput.files[0].name : "");
  statusDataZone?.classList.toggle("has-file", hasFile);
  if (statusDataLabel) {
    statusDataLabel.textContent = hasFile ? statusDataInput.files[0].name : "Upload Status Data";
  }
});

window.addEventListener("resize", debounce(() => chartManager.resizeVisible(), 120));
attachExportButtons();

