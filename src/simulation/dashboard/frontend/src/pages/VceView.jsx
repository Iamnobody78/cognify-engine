import React, { useEffect, useState } from 'react';
import { governanceApi } from '../services/api.js';

const SEV_CLS = { high: 'red', medium: 'orange', low: 'gray' };

export default function VceView() {
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [err, setErr] = useState('');

  const load = () => {
    governanceApi.vceLatest().then(setReport).catch(() => setReport(null));
    governanceApi.vceHistory().then(setHistory).catch((e) => setErr(String(e)));
  };

  useEffect(load, []);

  const rescan = async () => {
    setScanning(true);
    try {
      await governanceApi.vceScan();
      load();
    } catch (e) { setErr(String(e)); }
    setScanning(false);
  };

  const pol = report?.Polarization_Index ?? 0;
  const channel = report?.Verification_Channel || {};
  const poleCls = pol < 0.3 ? 'green' : pol < 0.6 ? 'orange' : 'red';

  return (
    <div>
      <h2>VCE 扫描可视化 <button className="link" onClick={rescan} disabled={scanning}>
        {scanning ? '扫描中…' : '立即重扫'}</button></h2>
      {err && <p className="error">{err}</p>}

      <div className="kpis">
        <div className="kpi">
          <div className="kpi-label">极化指数</div>
          <div className={`kpi-value ${poleCls}`}>{pol.toFixed(3)}</div>
          <div className={`badge ${poleCls}`}>{pol < 0.3 ? '低' : pol < 0.6 ? '中' : '高'}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">规则冲突</div>
          <div className="kpi-value">{report?.conflict_count ?? '—'}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">盲点</div>
          <div className="kpi-value">{report?.blindspot_count ?? '—'}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">验证通道</div>
          <div className={`kpi-value ${channel.enabled ? 'green' : 'red'}`}>
            {channel.enabled ? '启用' : '关闭'}</div>
          <div className="hint">validator: {channel.validator || 'none'}</div>
        </div>
      </div>

      <div className="two-col">
        <div>
          <h3>盲点趋势 (S65→S66 拐点)</h3>
          <table className="data-table">
            <thead><tr><th>#</th><th>时间</th><th>盲点</th><th>冲突</th><th>通道</th></tr></thead>
            <tbody>
              {[...history].reverse().map((h) => (
                <tr key={h.id}>
                  <td>{h.id}</td>
                  <td>{h.ts}</td>
                  <td><b>{h.blindspot_count}</b></td>
                  <td>{h.conflict_count}</td>
                  <td>{h.channel_enabled ? '✅' : '❌'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3>冲突列表</h3>
          {(report?.RuleConflicts || []).map((c, i) => (
            <div className="conflict-card" key={i}>
              <span className={`badge ${SEV_CLS[c.severity] || 'gray'}`}>{c.severity}</span>
              <span className="conflict-type">{c.type}</span>
              <span>规则: {c.rule || c.rules?.join(', ')}</span>
              <p className="hint">{c.description}</p>
            </div>
          ))}
          {(report?.RuleConflicts || []).length === 0 && <p className="hint">无冲突</p>}
        </div>
      </div>

      <h3>诚实边界</h3>
      <div className="boundary-box">
        <p><b>能检测:</b> {(report?.honest_boundary?.detects || []).join(' / ')}</p>
        <p><b>不能检测:</b> {(report?.honest_boundary?.does_not_detect || []).join(' / ')}</p>
        <p><b>盲点:</b> {(report?.BlindSpots || []).map((s) => s.category).join(', ') || '无 (已消除)'}</p>
      </div>
    </div>
  );
}
