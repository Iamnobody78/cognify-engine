import React, { useEffect, useState } from 'react';
import { governanceApi } from '../services/api.js';

export default function PolicyEditorView() {
  const [tree, setTree] = useState({ modules: {} });
  const [protocol, setProtocol] = useState('');
  const [yamlText, setYamlText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [validation, setValidation] = useState(null);
  const [deployResult, setDeployResult] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    governanceApi.policies().then((t) => {
      setTree(t);
      const first = Object.keys(t.modules || {})[0];
      if (first) { setProtocol(first); loadSource(first); }
    }).catch((e) => setErr(String(e)));
  }, []);

  const loadSource = async (name) => {
    try {
      const src = await governanceApi.protocolSource(name);
      setYamlText(src.yaml);
      setLoaded(true);
      setValidation(null);
      setDeployResult(null);
    } catch (e) { setErr(String(e)); }
  };

  const selectProtocol = (name) => {
    setProtocol(name);
    loadSource(name);
  };

  const doValidate = async () => {
    setErr(''); setDeployResult(null);
    try {
      const r = await governanceApi.policyValidate({ protocol, yaml: yamlText });
      setValidation(r);
    } catch (e) { setErr(String(e)); }
  };

  const doDeploy = async () => {
    setErr('');
    try {
      const r = await governanceApi.policyDeploy({ protocol, yaml: yamlText });
      setDeployResult(r);
      governanceApi.policies().then(setTree).catch(() => {});
    } catch (e) {
      if (e.message.startsWith('422')) {
        const detail = JSON.parse(e.message.slice(4));
        setDeployResult(detail);
      } else setErr(String(e));
    }
  };

  return (
    <div>
      <h2>策略编辑器</h2>
      <p className="hint">11 列声明式协议 (schema_version: 11-col-v1) — 编辑 → 预编译验证 → 部署（写入 config/protocols + 网关热重载）</p>
      {err && <p className="error">{err}</p>}
      <div className="filters">
        <select value={protocol} onChange={(e) => selectProtocol(e.target.value)}>
          {Object.keys(tree.modules || {}).map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <button onClick={doValidate}>验证</button>
        <button onClick={doDeploy} className="deploy">部署</button>
        <span className="hint">{loaded ? '已加载: ' + protocol : ''}</span>
      </div>
      <textarea className="yaml-editor" rows="26"
                value={yamlText}
                onChange={(e) => { setYamlText(e.target.value); setValidation(null); }} />
      {validation && (
        <div className={validation.valid ? 'result-box ok' : 'result-box bad'}>
          <p><b>{validation.valid ? '✅ 验证通过' : '❌ 验证失败'}</b>
            {validation.valid && ` — 编译规则 ${validation.rules_count} 条 (${(validation.rule_types || []).join(', ')})`}</p>
          {(validation.errors || []).map((e, i) => <p key={i} className="error">· {e}</p>)}
        </div>
      )}
      {deployResult && (
        <div className={deployResult.deployed ? 'result-box ok' : 'result-box bad'}>
          <p><b>{deployResult.deployed ? '🚀 部署成功' : '⛔ 部署被拒'}</b>
            {deployResult.deployed && ` — 网关热重载: 全网关 ${deployResult.rules_count} 条规则 (${protocol} × ${deployResult.protocol_rules})`}
            {!deployResult.deployed && deployResult.error && ` — ${deployResult.error}`}</p>
        </div>
      )}
    </div>
  );
}
