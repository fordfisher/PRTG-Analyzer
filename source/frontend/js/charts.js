import { clamp, setHtmlIfChanged } from "./utils.js";

/** Bar color by impact level (reuse app palette). */
const IMPACT_COLORS = {
  "Very low": "#22c55e",
  "Low": "#00ff9c",
  "Medium": "#eab308",
  "High": "#ff6b6b",
  "Very High": "#ef4444",
};

const IMPACT_ORDER = ["Very low", "Low", "Medium", "High", "Very High"];

/**
 * Build sensor-type categories and bar data from probe impact_distribution.
 * Returns { categories: string[], barData: { value, itemStyle }[] } sorted by impact (very low → very high) then by sensor type name.
 */
function buildProbeSensorTypeBars(impactDistribution) {
  const dist = impactDistribution || {};
  const entries = [];
  for (const level of IMPACT_ORDER) {
    const levelData = dist[level];
    const sensors = levelData?.sensors || {};
    for (const [sensorType, count] of Object.entries(sensors)) {
      const n = Number(count) || 0;
      if (n > 0) entries.push({ name: sensorType, impact: level, value: n });
    }
  }
  entries.sort((a, b) => {
    const ai = IMPACT_ORDER.indexOf(a.impact);
    const bi = IMPACT_ORDER.indexOf(b.impact);
    if (ai !== bi) return ai - bi;
    return (a.name || "").localeCompare(b.name || "");
  });
  const categories = entries.map((e) => e.name);
  const barData = entries.map((e) => ({
    value: e.value,
    itemStyle: { color: IMPACT_COLORS[e.impact] || "#b4c6ff" },
  }));
  return { categories, barData };
}

function chartAvailable(element) {
  return !!(window.echarts && element && element.offsetWidth && element.offsetHeight);
}

function toggleTabMessage(tabId, message) {
  const tab = document.getElementById(tabId);
  if (!tab) return;
  let existing = tab.querySelector(".tab-message");
  if (!message) {
    existing?.remove();
    return;
  }
  if (!existing) {
    existing = document.createElement("div");
    existing.className = "tab-message";
    tab.appendChild(existing);
  }
  existing.textContent = message;
}

export class ChartManager {
  constructor() {
    this.instances = new Map();
  }

  getOrCreate(id) {
    const element = document.getElementById(id);
    if (!chartAvailable(element)) return null;
    const existing = window.echarts.getInstanceByDom(element);
    const chart = existing || window.echarts.init(element);
    this.instances.set(id, chart);
    return chart;
  }

  /** Dispose chart by id so next getOrCreate returns a fresh instance. Use when data must fully refresh (e.g. sensor-type chart on timeframe change). */
  disposeChart(id) {
    const chart = this.instances.get(id);
    if (chart && !chart.isDisposed?.()) {
      chart.dispose();
    }
    this.instances.delete(id);
  }

  disposeRemoved() {
    for (const [id, chart] of this.instances.entries()) {
      if (!chart || chart.isDisposed?.()) {
        this.instances.delete(id);
        continue;
      }
      const element = chart.getDom?.();
      if (!element || !document.body.contains(element)) {
        chart.dispose();
        this.instances.delete(id);
      }
    }
  }

  resizeVisible() {
    for (const chart of this.instances.values()) {
      const element = chart.getDom?.();
      if (element && element.offsetWidth && element.offsetHeight) {
        chart.resize();
      }
    }
  }

  ensureOverviewLayout() {
    const element = document.getElementById("overview-charts");
    if (!element) return;
    const exportRow = (id) =>
      `<div class="chart-export-row"><label><input type="checkbox" class="chart-export-checkbox" data-export-chart-id="${id}" /> Include in report</label></div>`;
    setHtmlIfChanged(
      element,
      `<div class="overview-grid">
        <div class="chart"><div class="chart-header">Stability Radar</div><div class="chart-subtitle">Combined risk from errors, restarts, startup, threads and load.</div>${exportRow("stability-radar")}<div id="chart-stability-radar" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">ERP Load Orbit</div><div class="chart-subtitle">Approximate total ERP load versus safe capacity across probes.</div>${exportRow("erp-orbit")}<div id="chart-erp-orbit" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">Memory Utilization</div><div class="chart-subtitle">Physical RAM usage on the PRTG core server.</div>${exportRow("ram-usage")}<div id="chart-ram-usage" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">Sensor Impact Levels</div><div class="chart-subtitle">Distribution of sensors by performance impact on the system.</div>${exportRow("impact-donut")}<div id="chart-impact-donut" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">ERP Hot Probes</div><div class="chart-subtitle">Top probes by ERP load.</div>${exportRow("erp-hot-probes")}<div id="chart-erp-hot-probes" class="chart-inner"></div></div>
      </div>`
    );
  }

  renderOverview(vm) {
    this.ensureOverviewLayout();
    const { core, result, timelinePoints, probesByErp } = vm;

    const radarChart = this.getOrCreate("chart-stability-radar");
    if (radarChart) {
      const values = [
        clamp((Number(core.total_errors || 0) + Number(core.total_warnings || 0)) / 10, 0, 100),
        clamp(Number(core.total_restarts || 0) * 10, 0, 100),
        clamp((Number(core.startup_duration_sec || 0) / 60) * 20, 0, 100),
        clamp((Number(core.max_thread_runtime || 0) / 60) * 10, 0, 100),
        clamp(Number(result.calculated_requests_per_min || 0) / 150, 0, 100),
      ];
      radarChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "item" },
        radar: {
          indicator: [
            { name: "Errors", max: 100 },
            { name: "Restarts", max: 100 },
            { name: "Startup", max: 100 },
            { name: "Threads", max: 100 },
            { name: "Load", max: 100 },
          ],
          splitArea: { areaStyle: { color: ["rgba(8,20,40,0.9)", "rgba(5,17,35,0.9)"] } },
          axisName: { color: "#b4c6ff" },
        },
        series: [{ type: "radar", areaStyle: { opacity: 0.35 }, lineStyle: { color: "#22c55e" }, itemStyle: { color: "#22c55e" }, data: [{ value: values, name: "Risk profile" }] }],
      });
    }

    const orbitChart = this.getOrCreate("chart-erp-orbit");
    if (orbitChart) {
      const rpm = Number(result.calculated_requests_per_min || 0);
      const safeTotal = (Number(core.total_probes || 0) || 1) * 10000;
      const loadPct = clamp(safeTotal > 0 ? (rpm * 100) / safeTotal : 0, 0, 200);
      const color = loadPct > 150 ? "#ef4444" : loadPct > 100 ? "#eab308" : "#22c55e";
      orbitChart.setOption({
        backgroundColor: "transparent",
        tooltip: { formatter: () => `Estimated load: ${rpm.toFixed(0)} req/min<br/>Safe capacity: ${safeTotal.toLocaleString()} req/min` },
        series: [{
          type: "gauge",
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 200,
          axisLine: { lineStyle: { width: 10, color: [[1, "rgba(34,197,94,0.4)"]] } },
          progress: { show: true, width: 10, itemStyle: { color } },
          pointer: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: { formatter: () => `${loadPct.toFixed(0)}% load`, color: "#e4f0ff", fontSize: 16 },
          data: [{ value: loadPct }],
        }],
      });
    }

    const ramChart = this.getOrCreate("chart-ram-usage");
    if (ramChart) {
      const totalRam = Number(core.total_ram_mb || 0);
      const freeRam = Number(core.free_ram_mb || 0);
      const usedPct = clamp(totalRam > 0 ? ((totalRam - freeRam) * 100) / totalRam : 0, 0, 100);
      const color = usedPct > 90 ? "#ef4444" : usedPct > 75 ? "#eab308" : "#22c55e";
      ramChart.setOption({
        backgroundColor: "transparent",
        series: [{
          type: "gauge",
          startAngle: 210,
          endAngle: -30,
          min: 0,
          max: 100,
          axisLine: { lineStyle: { width: 8, color: [[1, "rgba(15,23,42,0.9)"]] } },
          progress: { show: true, width: 8, itemStyle: { color } },
          pointer: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: { formatter: () => `${usedPct.toFixed(0)}% used`, color: "#e4f0ff", fontSize: 14 },
          data: [{ value: usedPct }],
        }],
      });
    }

    const impactChart = this.getOrCreate("chart-impact-donut");
    if (impactChart) {
      const data = Object.entries(core.global_impact_distribution || {}).map(([name, info]) => ({ name, value: info?.total || 0 }));
      impactChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "item" },
        legend: { textStyle: { color: "#b4c6ff" } },
        series: [{ type: "pie", radius: ["45%", "70%"], center: ["50%", "50%"], label: { color: "#e4f0ff" }, data }],
      });
    }

    const hotChart = this.getOrCreate("chart-erp-hot-probes");
    if (hotChart) {
      hotChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: 120, right: 16, top: 20, bottom: 32 },
        xAxis: { type: "value", axisLabel: { color: "#b4c6ff" } },
        yAxis: { type: "category", data: probesByErp.slice(0, 8).map((probe) => probe.name || ""), axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "bar", data: probesByErp.slice(0, 8).map((probe) => Number(probe.erp || 0)), itemStyle: { color: "#3b82f6" } }],
      });
    }

    toggleTabMessage("tab-overview", null);
    this.disposeRemoved();
  }

  renderSensors(vm) {
    const { refreshBuckets, sensorCountByType, probeImpactCharts, hiddenProbeCount, showProbeDistribution } = vm;

    const intervalsChartEl = document.getElementById("chart-intervals");
    if (intervalsChartEl) {
      intervalsChartEl.style.display = showProbeDistribution ? "" : "none";
    }
    const intervalsChart = showProbeDistribution ? this.getOrCreate("chart-intervals") : null;
    if (intervalsChart) {
      intervalsChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: refreshBuckets.map((bucket) => bucket.interval_label), axisLabel: { color: "#b4c6ff", rotate: 30 } },
        yAxis: { type: "value", name: "Sensor count", nameTextStyle: { color: "#9fb5ff" }, axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "bar", data: refreshBuckets.map((bucket) => bucket.count), itemStyle: { color: "#00ff9c" } }],
      });
      if (typeof intervalsChart.resize === "function") intervalsChart.resize();
    }

    // Dispose and recreate so every bar (including bottom/last) updates when timeframe changes (e.g. oracletablespace).
    this.disposeChart("chart-erp-sensor-types");
    const sensorTypesContainer = document.getElementById("chart-erp-sensor-types");
    const sensorTypesChart = this.getOrCreate("chart-erp-sensor-types");
    if (sensorTypesChart && sensorTypesContainer) {
      const barCount = (sensorCountByType || []).length;
      const barHeightPx = 28;
      const minHeight = 260;
      const maxHeight = 800;
      const height = clamp(barCount * barHeightPx, minHeight, maxHeight);
      sensorTypesContainer.style.minHeight = `${height}px`;
      sensorTypesChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: 120, right: 20, top: 20, bottom: 40 },
        xAxis: { type: "value", name: "Sensor count", nameTextStyle: { color: "#9fb5ff" }, axisLabel: { color: "#b4c6ff" } },
        yAxis: { type: "category", data: sensorCountByType.map((entry) => entry.name), axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "bar", data: sensorCountByType.map((entry) => entry.value), itemStyle: { color: "#ff6b6b" } }],
      });
      sensorTypesChart.resize();
    }

    const container = document.getElementById("probe-impact-container");
    if (container) {
      if (!showProbeDistribution) {
        setHtmlIfChanged(container, "");
        container.style.display = "none";
      } else {
        container.style.display = "";
        const addAllMarkup =
          probeImpactCharts.length > 1
            ? `<div class="probe-charts-export-actions"><button type="button" class="probe-add-all-btn">Add all to report</button></div>`
            : "";
        const markup = `${addAllMarkup}${probeImpactCharts
        .map(
          (probe) => `<div class="probe-chart-card">
              <div class="probe-chart-title">${probe.name || ""}</div>
              <div class="chart-export-row"><label><input type="checkbox" class="chart-export-checkbox" data-export-chart-id="probe-impact-${probe.probe_id}" /> Include in report</label></div>
              <div id="probe-impact-${probe.probe_id}" class="chart probe-impact-chart"></div>
            </div>`
        )
        .join("")}${hiddenProbeCount ? `<div class="tab-message">Showing top 10 probe impact charts. ${hiddenProbeCount} additional probes remain in the table below.</div>` : ""}`;
        setHtmlIfChanged(container, markup);

        for (const probe of probeImpactCharts) {
          const chart = this.getOrCreate(`probe-impact-${probe.probe_id}`);
          if (!chart) continue;
          const { categories, barData } = buildProbeSensorTypeBars(probe.impact_distribution);
          chart.setOption({
            backgroundColor: "transparent",
            tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
            grid: { left: 72, right: 16, top: 20, bottom: 32 },
            xAxis: { type: "category", data: categories, axisLabel: { color: "#b4c6ff" } },
            yAxis: { type: "value", axisLabel: { color: "#b4c6ff" } },
            series: [{ type: "bar", data: barData }],
          });
        }
      }
    }

    toggleTabMessage("tab-sensors", !vm.probes.length && !refreshBuckets.length && !(vm.sensorCountByType && vm.sensorCountByType.length) ? "No probe or interval summary found in this Core.log." : null);
    this.disposeRemoved();
  }

  renderTimeline(vm) {
    const timelineChart = this.getOrCreate("chart-timeline");
    if (timelineChart) {
      timelineChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "item", formatter: (params) => `${params.value[0]}<br/>${params.value[2]}` },
        xAxis: { type: "time", axisLabel: { color: "#b4c6ff" } },
        yAxis: { type: "value", min: -0.5, max: 1.5, axisLabel: { show: false }, splitLine: { show: false } },
        series: [{
          type: "scatter",
          symbolSize: 10,
          data: vm.timelinePoints.filter((point) => point?.timestamp).map((point) => [point.timestamp, point.kind === "restart" ? 1 : 0, point.label]),
          itemStyle: { color: "#7df9ff" },
        }],
      });
    }

    toggleTabMessage("tab-timeline", vm.timelinePoints.length ? null : "No timeline events detected in this Core.log.");
    this.disposeRemoved();
  }

  renderTab(tabId, vm) {
    if (tabId === "overview") this.renderOverview(vm);
    if (tabId === "sensors") this.renderSensors(vm);
    if (tabId === "timeline") this.renderTimeline(vm);
  }
}
