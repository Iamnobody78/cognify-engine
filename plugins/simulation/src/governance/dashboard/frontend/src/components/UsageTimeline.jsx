import React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function UsageTimeline({ buckets }) {
  if (!buckets?.length) return <div className="panel">无时间线数据</div>;
  const data = buckets.map((b) => ({
    bucket: b.bucket,
    调用量: b.calls,
    错误: b.errors,
  }));
  return (
    <div className="panel">
      <h3>调用量时间线</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="bucket" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Legend />
          <Bar dataKey="调用量" fill="#4f8cff">
            {data.map((d, i) => (
              <Cell key={i} fill={d.错误 > 0 ? "#ff6b6b" : "#4f8cff"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
