/** Chart IDs that can be included in the HTML report export. */
export const EXPORTABLE_CHART_IDS = [
  "stability-radar",
  "erp-orbit",
  "ram-usage",
  "impact-donut",
  "erp-hot-probes",
  "intervals",
  "sensor-types",
  "timeline",
];

const state = {
  lastHash: null,
  lastResult: null,
  lastFullResult: null,
  showTopErrorsCount: 5,
  globalTimeFrame: "all",
  exportSelectedErrorPatterns: [],
  exportSelectedCharts: [...EXPORTABLE_CHART_IDS],
  exportIncludeFindings: true,
  exportSelectedFindings: [],
  activeTab: "overview",
  timeframeResults: new Map(),
};

export function getState() {
  return state;
}

export function updateState(patch) {
  Object.assign(state, patch);
  return state;
}

export function resetResultState(result, hash) {
  state.lastHash = hash || null;
  state.lastResult = result;
  state.lastFullResult = result;
  state.globalTimeFrame = result?.status_snapshot ? "now" : "all";
  state.exportSelectedErrorPatterns = [];
  state.exportSelectedCharts = [...EXPORTABLE_CHART_IDS];
  state.exportIncludeFindings = true;
  const findings = result?.findings || [];
  state.exportSelectedFindings = findings.map((_, i) => i);
  state.timeframeResults = new Map([["all", result]]);
}
