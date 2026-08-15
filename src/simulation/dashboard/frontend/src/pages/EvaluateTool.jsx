import React, { useState } from 'react';
import { governanceApi } from '../services/api.js';
import { ActionBadge } from './AgentsView.jsx';

const DEFAULT_BODY = `{
  "governance": {
    "protocols": {
      "feynman_test": { "satisfied": true }
    }
  }
}`;

export default function EvaluateTool() {
  const [agentId, setAgentId] = useState('agent-solver-b');
  const [bodyText, setBodyText] = useState(DEFAULT_BODY);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState('');

  const run = async () => {
    setErr('');
    try {
      const body = JSON.parse(bodyText);
      const out = await governanceApi.evaluate({ agent_id: agentId, path: '/gateway', method: 'POST', body });
      setResult(out);
    } catch (e) { setErr(String(e)); }
  };

  return (
    <div>
      <h2>实时裁决试炼（开发工具）</h2>
      <p className="hint">演示谎报缓解: 裸 <code>{'{"satisfied": true}'}</code> → 验证失败 → ESCALATE 降级</p>
      <div className="eval-form">
        <label>agent_id
          <input value={agentId} onChange={(e) => setAgentId(e.target.value)} />
        </label>
        <label>请求体 (JSON)
          <textarea rows="10" value={bodyText} onChange={(e) => setBodyText(e.target.value)} />
        </label>
        <button onClick={run}>执行裁决</button>
      </div>
      {err && <p className="error">{err}</p>}
      {result && (
        <div className="result-box">
          <p>
            命中规则: <b>{result.rule}</b> |
            最终动作: <ActionBadge action={result.action} /> |
            通道: {result.channel}
          </p>
          {result.action === 'ESCALATE' && result.verification?.validator === 'baseline' && (
            <p className="warn">⚠ 放行声明未通过独立验证 — 已降级为升级复核（谎报缓解）</p>
          )}
          <pre>{JSON.stringify(result.verification, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
