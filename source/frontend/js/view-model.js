import { filterTimelineByWindow, parseTimestamp, formatDateTime } from "./utils.js?v=1.3";

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

function buildErpByType(core) {
  const impactWeights = {
    "Very low": 1,
    "Very Low": 1,
    Low: 2,
    Medium: 3,
    High: 4,
    "Very High": 5,
    "Very high": 5,
  };

  const totals = {};
  const counts = {};
  for (const [level, info] of Object.entries(core?.global_impact_distribution || {})) {
    const weight = impactWeights[level] || 1;
    for (const [sensorType, count] of Object.entries(info?.sensors || {})) {
      const numericCount = Number(count) || 0;
      if (!numericCount) continue;
      totals[sensorType] = (totals[sensorType] || 0) + weight * numericCount;
      counts[sensorType] = (counts[sensorType] || 0) + numericCount;
    }
  }

  const impactFactor = {};
  for (const [sensorType, totalCount] of Object.entries(counts)) {
    impactFactor[sensorType] = totalCount > 0 ? (totals[sensorType] || 0) / totalCount : 1;
  }

  const erpByType = {};
  for (const [intervalKey, info] of Object.entries(core?.interval_distribution || {})) {
    const seconds = Number(intervalKey);
    if (!seconds || seconds <= 0) continue;
    for (const [sensorType, count] of Object.entries(info?.sensors || {})) {
      const numericCount = Number(count) || 0;
      if (!numericCount) continue;
      const baseLoad = (numericCount * 60) / seconds;
      erpByType[sensorType] = (erpByType[sensorType] || 0) + baseLoad * (impactFactor[sensorType] || 1);
    }
  }

  return Object.entries(erpByType)
    .map(([name, value]) => ({ name, value: Number(value.toFixed(2)) }))
    .sort((left, right) => right.value - left.value)
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
    probeImpactCharts: probesBySensorCount.slice(0, 10),
    hiddenProbeCount: Math.max(0, probes.length - 10),
    aggregatedErrors,
    visibleErrors: aggregatedErrors.slice(0, state.showTopErrorsCount),
    timelinePoints,
    errorCountLabel: aggregatedErrors.length
      ? `Showing 1-${Math.min(state.showTopErrorsCount, aggregatedErrors.length)} of ${aggregatedErrors.length}`
      : "No errors",
    erpByType: buildErpByType(core),
    refreshBuckets: Array.isArray(result?.refresh_rate_distribution) ? result.refresh_rate_distribution : [],
    segments: Array.isArray(core.error_patterns_by_segment) ? core.error_patterns_by_segment : [],
  };
}
