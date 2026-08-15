import React, { useEffect, useState } from 'react';
import { governanceApi } from '../services/api.js';
import { ActionBadge } from './AgentsView.jsx';

export default function AuditView() {
  const [events, setEvents] = useState([]);
  const [filters, setFilters] = useState({ action: '', rule: '', agent: '', channel: '' });
  const [openId, setOpenId] = useState(null);
  const [err, setErr] = useState('');

  const load = (f = filters) => {
    const params = { limit: 100 };
    if (f.action) params.action = f.action;
    if (f.rule) params.rule = f.rule;
    if (f.agent) params.agent = f.agent;
    if (f.channel) params.channel = f.channel;
    governanceApi.audit(params).then(setEvents).catch((e) => setErr(String(e)));
  };

  useEffect(() => { load(); }, []);

  return (
    <div>
      <h2>审计查看</h2>
      <div className="filters">
        <input placeholder="agent_id" value={filters.agent}
               onChange={(e) => setFilters({ ...filters, agent: e.target.value })} />
        <input placeholder="规则名 (可模糊)" value={filters.rule}
               onChange={(e) => setFilters({ ...filters, rule: e.target.value })} />
        <select value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })}>
          <option value="">全部动作</option>
          <option>DENY</option><option>ESCALATE</option>
          <option>ALLOW_WITH_WARNING</option>
        </select>
        <button onClick={() => load()}>查询</button>
      </div>
      {err && <p className="error">{err}</p>}
      <table className="data-table">
        <thead>
          <tr><th>ID</th><th>时间</th><th>agent</th><th>规则</th><th>动作</th>
              <th>通道</th><th>验证</th><th>置信度</th></tr>
        </thead>
        <tbody>
          {events.map((e) => {
            const v = e.verification || {};
            const downgraded = e.action === 'ESCALATE' && v.validator === 'baseline';
            return (
              <React.Fragment key={e.id}>
                <tr className="clickable" onClick={() => setOpenId(openId === e.id ? null : e.id)}>
                  <td>{e.id}</td>
                  <td>{e.ts}</td>
                  <td>{e.agent_id}</td>
                  <td>{e.matched_rule}</td>
                  <td>
                    <ActionBadge action={e.action} />
                    {downgraded && <span className="warn"> ⚠ 声明未通过验证</span>}
                  </td>
                  <td>{e.channel}</td>
                  <td>{v.verified === true ? '✅' : v.verified === false ? '❌' : '—'}</td>
                  <td>{v.confidence ?? '—'}</td>
                </tr>
                {openId === e.id && (
                  <tr><td colSpan="8" className="detail-row">
                    <pre>{JSON.stringify(e.verification, null, 2)}</pre>
                    <pre className="body">{JSON.stringify(e.raw_body, null, 2)}</pre>
                  </td></tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
