import React from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function HypothesisPanel({ summary, trend }) {
  if (!summary?.variants?.length) return <div className="panel">无假设数据</div>;

  // latest cumulative point per variant (line chart series)
  const seriesData = (trend?.trend ?? []).map((t) => ({
    ...t,
    ts: new Date(t.ts).toLocaleDateString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
    }),
  }));

  const variants = summary.variants;
  const colors = ["#4f8cff", "#ffb84f", "#4ade80", "#c084fc"];

  return (
    <div className="panel">
      <h3>假设命中率趋势 (variant 聚合)</h3>
      <div className="variant-grid">
        {variants.map((v, i) => (
          <div key={v.variant_id} className="variant-card">
            <div className="variant-id">{v.variant_id}</div>
            <div className="health-big">{Math.round((v.confidence ?? 0) * 100)}%</div>
            <div className="health-meta">
              attempts {v.attempts} · hits {v.hits}
            </div>
          </div>
        ))}
      </div>
      {seriesData.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={seriesData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            {variants.map((v, i) => (
              <Line
                key={v.variant_id}
                type="monotone"
                dataKey="cumulative_attempts"
                name={`${v.variant_id} (attempts)`}
                stroke={colors[i % colors.length]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
