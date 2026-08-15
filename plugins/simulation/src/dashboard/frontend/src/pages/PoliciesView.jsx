import React, { useEffect, useState } from 'react';
import { governanceApi } from '../services/api.js';

const TYPE_LABEL = { ethics: '伦理 (DENY)', enforce: '强制执行 (ESCALATE)', ok: '放行 (ALLOW_WARNING)' };
const TYPE_CLS = { ethics: 'col-ethics', enforce: 'col-enforce', ok: 'col-ok' };
const SEV_CLS = { high: 'red', medium: 'orange', low: 'gray' };

export default function PoliciesView() {
  const [tree, setTree] = useState({ modules: {} });
  const [openMce, setOpenMce] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    governanceApi.policies().then(setTree).catch((e) => setErr(String(e)));
  }, []);

  return (
    <div>
      <h2>策略管理</h2>
      {err && <p className="error">{err}</p>}
      {Object.entries(tree.modules || {}).map(([protocol, mod]) => (
        <div className="protocol-card" key={protocol}>
          <h3>协议: {protocol}</h3>
          <div className="rule-columns">
            {['ethics', 'enforce', 'ok'].map((t) => (
              <div className={`rule-col ${TYPE_CLS[t]}`} key={t}>
                <div className="col-title">{TYPE_LABEL[t]}</div>
                {mod.rules.filter((r) => r.rule_type === t).map((r) => (
                  <div className="rule-entry" key={r.rule_name}>
                    <div className="rule-head">
                      <span className="rule-name">{r.rule_name}</span>
                      <span className="priority">p={r.priority}</span>
                    </div>
                    {r.conflicts.length > 0 && (
                      <span className="badge orange" title={r.conflicts[0].description}>
                        ⚠ 冲突
                      </span>
                    )}
                    <pre className="rule-pattern">{r.json_pattern || r.json_path}</pre>
                    <button className="link" onClick={() => setOpenMce(openMce === r.rule_name ? null : r.rule_name)}>
                      {openMce === r.rule_name ? '收起' : '为什么存在?'}
                    </button>
                    {openMce === r.rule_name && r.mce && (
                      <div className="mce-box">
                        <p><b>why_exists:</b> {r.mce.why_exists}</p>
                        <p><b>governs:</b> {r.mce.what_it_governs}</p>
                        <p><b>origin:</b> {r.origin}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
