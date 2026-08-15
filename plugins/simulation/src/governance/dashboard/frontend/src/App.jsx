import React, { useEffect, useState } from "react";
import {
  fetchHealth,
  fetchHypSummary,
  fetchHypTrend,
  fetchLatencyOutliers,
  fetchTimeline,
  fetchUsageSummary,
} from "./api.js";
import HealthCards from "./components/HealthCards.jsx";
import HypothesisPanel from "./components/HypothesisPanel.jsx";
import LatencyTable from "./components/LatencyTable.jsx";
import UsageTimeline from "./components/UsageTimeline.jsx";

export default function App() {
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState(null);
  const [outliers, setOutliers] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [hypSum, setHypSum] = useState(null);
  const [hypTrend, setHypTrend] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchHealth(),
      fetchUsageSummary(),
      fetchLatencyOutliers(2000),
      fetchTimeline("day"),
      fetchHypSummary(),
      fetchHypTrend(),
    ])
      .then(
        ([h, s, o, t, hs, ht]) => {
          setHealth(h.servers);
          setSummary(s);
          setOutliers(o);
          setTimeline(t);
          setHypSum(hs);
          setHypTrend(ht);
        }
      )
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>MCP Governance Dashboard</h1>
        <span className="subtitle">
          BottleSumo Meta-Harness · 治理监控 (SEED-ROUND-1)
        </span>
      </header>
      <section className="section">
        <h2>服务器健康</h2>
        <HealthCards servers={health} loading={loading} error={error} />
      </section>
      <section className="section">
        <h2>工具延迟</h2>
        <LatencyTable summary={summary} outliers={outliers} />
      </section>
      <section className="section">
        <h2>调用量趋势</h2>
        <UsageTimeline buckets={timeline} />
      </section>
      <section className="section">
        <h2>假设命中率</h2>
        <HypothesisPanel summary={hypSum} trend={hypTrend} />
      </section>
      <footer className="app-footer">
        data: mcp_usage_report.jsonl (52) + hypotheses.jsonl (43) · Sprint 14 SEED-ROUND-1
      </footer>
    </div>
  );
}
