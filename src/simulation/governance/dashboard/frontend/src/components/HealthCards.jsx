import React from "react";

function fmtMs(ms) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(0)}ms`;
}

export default function HealthCards({ servers, loading, error }) {
  if (error) return <div className="panel error">加载失败: {error}</div>;
  if (loading) return <div className="panel">加载中…</div>;
  if (!servers?.length) return <div className="panel">无服务器数据</div>;

  return (
    <div className="health-grid">
      {servers.map((s) => (
        <div
          key={s.name}
          className={`panel health-card ${s.success_rate === 1 ? "ok" : s.success_rate >= 0.5 ? "warn" : "bad"}`}
        >
          <div className="health-name">{s.name}</div>
          <div className="health-big">{Math.round(s.success_rate * 100)}%</div>
          <div className="health-meta">
            调用 {s.calls} · ok {s.ok} · err {s.error}
          </div>
          <div className="health-meta">
            平均 {fmtMs(s.avg_ms)} · p95 {fmtMs(s.p95_ms)}
          </div>
          <div className="health-last">
            最近: {s.last_status ?? "-"} {s.last_ts ? new Date(s.last_ts).toLocaleString() : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
