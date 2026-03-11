const state = {
  lastHash: null,
  lastResult: null,
  lastFullResult: null,
  showTopErrorsCount: 5,
  globalTimeFrame: "all",
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
  state.timeframeResults = new Map([["all", result]]);
}
