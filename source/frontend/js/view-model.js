import { filterTimelineByWindow, parseTimestamp, formatDateTime } from "./utils.js";

function aggregateErrorsForTimeFrame(core, timeframe) {
  const segments = Array.isArray(core?.error_patterns_by_segment) ? core.error_patterns_by_segment : [];
  if (!segments.length) {
    const fallback = Array.isArray(core?.top_errors) ? core.top_errors : [];
    return fallback.map((entry, index) => ({ ...entry, rank: index + 1 }));
  }

  const count = timeframe === "all" ? segments.length : Math.min(parseInt(timeframe, 10) || 1, segments.length);
  const merged = {};
  for (let segIndex = 0; segIndex < count; segIndex += 1) {
    for (const entry of segments[segIndex] || []) {
      const pattern = entry.pattern;
      if (!merged[pattern]) {
        merged[pattern] = {
          pattern,
          count: 0,
          first_seen: entry.first_seen || "",
          last_seen: entry.last_seen || "",
          sample_lines: [],
        };
      }
      const target = merged[pattern];
      target.count += entry.count || 0;
      if (entry.first_seen && (!target.first_seen || entry.first_seen < target.first_seen)) {
        target.first_seen = entry.first_seen;
      }
      if (entry.last_seen && (!target.last_seen || entry.last_seen > target.last_seen)) {
        target.last_seen = entry.last_seen;
      }
      for (const sample of entry.sample_lines || []) {
        if (target.sample_lines.length < 5) {
          target.sample_lines.push(sample);
        }
      }
    }
  }

  return Object.values(merged)
    .sort((left, right) => (right.count || 0) - (left.count || 0))
    .map((entry, index) => ({ ...entry, rank: index + 1 }));
}

/** Exact sensor counts by type from core.log (sum across impact levels). No weighting or ERP. */
function buildSensorCountByType(core) {
  const counts = {};
  for (const info of Object.values(core?.global_impact_distribution || {})) {
    for (const [sensorType, count] of Object.entries(info?.sensors || {})) {
      const n = Number(count) || 0;
      if (n > 0) counts[sensorType] = (counts[sensorType] || 0) + n;
    }
  }
  return Object.entries(counts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 20);
}

/** Exact sensor counts by type from status snapshot (HTML impact_distribution). Used when "now" is selected. */
function buildSensorCountByTypeFromStatus(snapshot) {
  const dist = snapshot?.impact_distribution || {};
  const counts = {};
  for (const info of Object.values(dist)) {
    for (const [sensorType, count] of Object.entries(info?.sensors || {})) {
      const n = Number(count) || 0;
      if (n > 0) counts[sensorType] = (counts[sensorType] || 0) + n;
    }
  }
  return Object.entries(counts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 20);
}

function buildSliderModel(core) {
  const restarts = (core.restart_events || [])
    .slice()
    .sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
  const count = restarts.length;
  if (!count) return { steps: [], markers: [], max: 0, min: 1 };

  const firstMs = parseTimestamp(core.first_timestamp);
  const lastMs = parseTimestamp(core.last_timestamp);
  const span = lastMs - firstMs;

  const steps = [];
  for (let i = 1; i <= count; i++) {
    steps.push({ value: String(i), label: `Past ${i} restart${i > 1 ? "s" : ""}` });
  }
  steps.push({ value: "all", label: "All" });

  const markers = restarts.map((r, idx) => {
    const ms = parseTimestamp(r.timestamp);
    const pct = span > 0 ? ((ms - firstMs) / span) * 100 : (idx / Math.max(count - 1, 1)) * 100;
    return {
      pct,
      timestamp: r.timestamp,
      formatted: formatDateTime(r.timestamp),
      label: `Restart ${count - idx}`,
    };
  });

  return { steps, markers, max: count, min: 1 };
}

export function buildViewModel(result, state) {
  const core = result?.core || {};
  const fullCore = (state.lastFullResult || result)?.core || {};
  const fullResult = state.lastFullResult || result;
  const statusSnapshot = fullResult?.status_snapshot || null;
  const probes = Array.isArray(core.probes) ? core.probes : [];
  const probesBySensorCount = probes.slice().sort((left, right) => (right.sensor_count || 0) - (left.sensor_count || 0));
  const probesByErp = probes
    .slice()
    .filter((probe) => probe && probe.erp != null)
    .sort((left, right) => (right.erp || 0) - (left.erp || 0));
  const effectiveTimeFrame = state.globalTimeFrame === "now" ? "all" : state.globalTimeFrame;
  const aggregatedErrors = aggregateErrorsForTimeFrame(core, effectiveTimeFrame);
  const timelinePoints = filterTimelineByWindow(Array.isArray(result?.timeline) ? result.timeline : [], core, effectiveTimeFrame);
  const sliderModel = buildSliderModel(fullCore);

  const lastBootSnapshot = Array.isArray(fullCore.segment_snapshots) && fullCore.segment_snapshots.length
    ? fullCore.segment_snapshots[0]
    : null;

  const isNow = state.globalTimeFrame === "now";
  const sensorCountByType = isNow && statusSnapshot?.impact_distribution
    ? buildSensorCountByTypeFromStatus(statusSnapshot)
    : buildSensorCountByType(core);
  const showProbeDistribution = !isNow;
  const refreshBuckets = isNow ? [] : (Array.isArray(result?.refresh_rate_distribution) ? result.refresh_rate_distribution : []);

  return {
    result,
    core,
    sliderModel,
    statusSnapshot,
    hasStatusSnapshot: !!statusSnapshot,
    lastBootSnapshot,
    probes,
    probesBySensorCount,
    probesByErp,
    busiestProbe: probesByErp[0] || null,
    probeImpactCharts: showProbeDistribution ? probesBySensorCount.slice(0, 10) : [],
    hiddenProbeCount: showProbeDistribution ? Math.max(0, probes.length - 10) : 0,
    aggregatedErrors,
    visibleErrors: aggregatedErrors.slice(0, state.showTopErrorsCount),
    timelinePoints,
    errorCountLabel: aggregatedErrors.length
      ? `Showing 1-${Math.min(state.showTopErrorsCount, aggregatedErrors.length)} of ${aggregatedErrors.length}`
      : "No errors",
    sensorCountByType,
    refreshBuckets,
    showProbeDistribution,
    segments: Array.isArray(core.error_patterns_by_segment) ? core.error_patterns_by_segment : [],
  };
}
