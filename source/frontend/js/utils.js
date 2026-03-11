export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function setHtmlIfChanged(element, html) {
  if (!element) return;
  if (element.innerHTML !== html) {
    element.innerHTML = html;
  }
}

export function filterTimelineByWindow(points, core, timeframe) {
  if (!timeframe || timeframe === "all" || !Array.isArray(points) || points.length === 0) {
    return Array.isArray(points) ? points : [];
  }

  const restarts = (core?.restart_events || [])
    .slice()
    .sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
  const count = parseInt(timeframe, 10);
  if (!(count >= 1) || restarts.length < count) {
    return Array.isArray(points) ? points : [];
  }

  const windowStart = restarts[restarts.length - count]?.timestamp || "";
  return points.filter((point) => (point?.timestamp || "") >= windowStart);
}

export function parseTimestamp(ts) {
  if (!ts) return NaN;
  try {
    return new Date(ts.replace(" ", "T")).getTime();
  } catch {
    return NaN;
  }
}

export function formatDateTime(ts) {
  const ms = typeof ts === "number" ? ts : parseTimestamp(ts);
  if (!ms || Number.isNaN(ms)) return "";
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function debounce(fn, delayMs) {
  let timeoutId = 0;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => fn(...args), delayMs);
  };
}
