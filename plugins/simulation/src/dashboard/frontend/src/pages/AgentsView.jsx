import React, { useEffect, useState } from 'react';
import { governanceApi } from '../services/api.js';

const STATUS_COLORS = { active: 'green', idle: 'gray', suspended: 'red' };

export default function AgentsView() {
  const [agents, setAgents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [audit, setAudit] = useState([]);
  const [err, setErr] = useState('');

  useEffect(() => {
    governanceApi.agents().then(setAgents).catch((e) => setErr(String(e)));
  }, []);

  const openAudit = async (agentId) => {
    setSelected(agentId);
    const rows = await governanceApi.agentAudit(agentId);
    setAudit(rows);
  };

  return (
    <div>
      <h2>代理清单</h2>
      {err && <p className="error">{err}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th><th>名称</th><th>角色</th><th>状态</th>
            <th>会话数</th><th>升级</th><th>验证通过</th><th>验证失败 ⚠</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.id} onClick={() => openAudit(a.id)} className="clickable">
              <td>{a.id}</td>
              <td>{a.name}</td>
              <td>{a.role}</td>
              <td>
                <span className={`badge ${STATUS_COLORS[a.status] || 'gray'}`}>{a.status}</span>
              </td>
              <td>{a.sessions}</td>
              <td>{a.escalations}</td>
              <td>{a.verified_ok}</td>
              <td>{a.verified_fail > 0
                ? <span className="warn">{a.verified_fail} ⚠</span> : a.verified_fail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">点击行查看该 agent 的审计流（验证失败 = 谎报嫌疑）</p>

      {selected && (
        <div className="modal">
          <div className="modal-box">
            <h3>审计流 — {selected}</h3>
            <button className="close" onClick={() => setSelected(null)}>×</button>
            <table className="data-table">
              <thead>
                <tr><th>ID</th><th>规则</th><th>动作</th><th>通道</th><th>验证</th></tr>
              </thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.matched_rule}</td>
                    <td><ActionBadge action={e.action} /></td>
                    <td>{e.channel}</td>
                    <td>{e.verification?.verified ? '✅' : '❌'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export function ActionBadge({ action }) {
  const cls = action === 'DENY' ? 'red' : action === 'ESCALATE' ? 'orange' : 'green';
  return <span className={`badge ${cls}`}>{action}</span>;
}
