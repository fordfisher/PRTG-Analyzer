import { clamp, setHtmlIfChanged } from "./utils.js?v=1.3";

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
    setHtmlIfChanged(
      element,
      `<div class="overview-grid">
        <div class="chart"><div class="chart-header">Stability Radar</div><div class="chart-subtitle">Combined risk from errors, restarts, startup, threads and load.</div><div id="chart-stability-radar" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">ERP Load Orbit</div><div class="chart-subtitle">Approximate total ERP load versus safe capacity across probes.</div><div id="chart-erp-orbit" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">Memory Utilization</div><div class="chart-subtitle">Physical RAM usage on the PRTG core server.</div><div id="chart-ram-usage" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">Sensor Impact Levels</div><div class="chart-subtitle">Distribution of sensors by performance impact on the system.</div><div id="chart-impact-donut" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">Error Activity Over Time</div><div class="chart-subtitle">Daily error volume based on timeline analysis.</div><div id="chart-error-shockwave" class="chart-inner"></div></div>
        <div class="chart"><div class="chart-header">ERP Hot Probes</div><div class="chart-subtitle">Top probes by ERP load.</div><div id="chart-erp-hot-probes" class="chart-inner"></div></div>
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

    const shockChart = this.getOrCreate("chart-error-shockwave");
    if (shockChart) {
      const buckets = {};
      for (const point of timelinePoints) {
        if (!point?.timestamp || point.kind !== "error") continue;
        const day = point.timestamp.slice(0, 10);
        buckets[day] = (buckets[day] || 0) + 1;
      }
      const entries = Object.entries(buckets).sort(([left], [right]) => (left < right ? -1 : 1));
      shockChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: entries.map(([day]) => day), axisLabel: { color: "#b4c6ff" } },
        yAxis: { type: "value", axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "line", data: entries.map(([, count]) => count), smooth: true, showSymbol: false, lineStyle: { color: "#22c55e" }, areaStyle: { opacity: 0.15, color: "#22c55e" } }],
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
    const { refreshBuckets, erpByType, probeImpactCharts, hiddenProbeCount } = vm;

    const intervalsChart = this.getOrCreate("chart-intervals");
    if (intervalsChart) {
      intervalsChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: refreshBuckets.map((bucket) => bucket.interval_label), axisLabel: { color: "#b4c6ff", rotate: 30 } },
        yAxis: { type: "value", axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "bar", data: refreshBuckets.map((bucket) => bucket.count), itemStyle: { color: "#00ff9c" } }],
      });
    }

    const erpTypesChart = this.getOrCreate("chart-erp-sensor-types");
    if (erpTypesChart) {
      erpTypesChart.setOption({
        backgroundColor: "transparent",
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: 120, right: 20, top: 20, bottom: 40 },
        xAxis: { type: "value", name: "Relative load", nameTextStyle: { color: "#9fb5ff" }, axisLabel: { color: "#b4c6ff" } },
        yAxis: { type: "category", data: erpByType.map((entry) => entry.name), axisLabel: { color: "#b4c6ff" } },
        series: [{ type: "bar", data: erpByType.map((entry) => entry.value), itemStyle: { color: "#ff6b6b" } }],
      });
    }

    const container = document.getElementById("probe-impact-container");
    if (container) {
      const markup = `${probeImpactCharts
        .map(
          (probe) => `<div class="probe-chart-card">
              <div class="probe-chart-title">${probe.name || ""}</div>
              <div id="probe-impact-${probe.probe_id}" class="chart probe-impact-chart"></div>
            </div>`
        )
        .join("")}${hiddenProbeCount ? `<div class="tab-message">Showing top 10 probe impact charts. ${hiddenProbeCount} additional probes remain in the table below.</div>` : ""}`;
      setHtmlIfChanged(container, markup);

      for (const probe of probeImpactCharts) {
        const chart = this.getOrCreate(`probe-impact-${probe.probe_id}`);
        if (!chart) continue;
        const dist = probe.impact_distribution || {};
        const levels = ["Very low", "Low", "Medium", "High", "Very High"];
        chart.setOption({
          backgroundColor: "transparent",
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
          grid: { left: 48, right: 16, top: 20, bottom: 32 },
          xAxis: { type: "category", data: levels, axisLabel: { color: "#b4c6ff" } },
          yAxis: { type: "value", axisLabel: { color: "#b4c6ff" } },
          series: [{ type: "bar", data: levels.map((level) => dist[level]?.total || 0), itemStyle: { color: "#00f5ff" } }],
        });
      }
    }

    toggleTabMessage("tab-sensors", !vm.probes.length && !refreshBuckets.length ? "No probe or interval summary found in this Core.log." : null);
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
