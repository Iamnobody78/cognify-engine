import React from "react";

function fmtMs(ms) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(0)}ms`;
}

export default function LatencyTable({ summary, outliers }) {
  const byTool = summary?.by_tool ?? [];
  return (
    <div className="panel">
      <h3>工具调用延迟分布</h3>
      {summary && (
        <div className="summary-strip">
          <span>总调用 {summary.total_calls}</span>
          <span>成功率 {Math.round(summary.success_rate * 100)}%</span>
          <span>avg {fmtMs(summary.avg_ms)}</span>
          <span>p95 {fmtMs(summary.p95_ms)}</span>
          <span>max {fmtMs(summary.max_ms)}</span>
        </div>
      )}
      <table className="latency-table">
        <thead>
          <tr>
            <th>工具</th>
            <th>调用</th>
            <th>avg</th>
            <th>p95</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          {byTool.map((t) => (
            <tr key={t.tool}>
              <td>{t.tool}</td>
              <td>{t.calls}</td>
              <td>{fmtMs(t.avg_ms)}</td>
              <td>{fmtMs(t.p95_ms)}</td>
              <td className={t.error ? "bad" : ""}>{t.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {outliers?.length > 0 && (
        <div className="outliers">
          <h4>异常调用 (慢 &gt;2s 或失败)</h4>
          <ul>
            {outliers.map((o, i) => (
              <li key={i} className="outlier-row">
                <span className="bad">{o.status !== "ok" ? "FAIL" : "SLOW"}</span>
                <span>{o.server} → {o.tool}</span>
                <span>{fmtMs(o.duration_ms)}</span>
                <span className="muted">
                  {new Date(o.ts).toLocaleString()} {o.error ?? ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
