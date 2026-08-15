const BASE = "/api";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`);
  }
  return res.json();
}

export const fetchHealth = () => get("/health");
export const fetchUsageSummary = () => get("/usage/summary");
export const fetchLatencyOutliers = (threshold = 2000) =>
  get(`/usage/latency?threshold=${threshold}`);
export const fetchTimeline = (bucket = "day") =>
  get(`/usage/timeline?bucket=${bucket}`);
export const fetchHypSummary = () => get("/hypotheses/summary");
export const fetchHypTrend = () => get("/hypotheses/trend");
