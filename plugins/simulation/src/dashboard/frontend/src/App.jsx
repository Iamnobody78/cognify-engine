import React, { useState } from 'react';
import AgentsView from './pages/AgentsView.jsx';
import PoliciesView from './pages/PoliciesView.jsx';
import AuditView from './pages/AuditView.jsx';
import VceView from './pages/VceView.jsx';
import EvaluateTool from './pages/EvaluateTool.jsx';
import PolicyEditorView from './pages/PolicyEditorView.jsx';
import LoginView from './pages/LoginView.jsx';
import { authApi } from './services/api.js';

const TABS = [
  { key: 'agents', label: '代理清单', view: AgentsView },
  { key: 'policies', label: '策略管理', view: PoliciesView },
  { key: 'editor', label: '策略编辑器', view: PolicyEditorView },
  { key: 'audit', label: '审计查看', view: AuditView },
  { key: 'vce', label: 'VCE 扫描', view: VceView },
  { key: 'eval', label: '实时裁决', view: EvaluateTool },
];

const ROLE_LABEL = { viewer: '只读', auditor: '审计员', admin: '管理员' };

export default function App() {
  const [user, setUser] = useState(authApi.getUser());
  const [token, setToken] = useState(authApi.getToken());
  const [tab, setTab] = useState('agents');

  // 路由守卫 (ARCH-ROUND 2 / GAP-3.1): 无 token → 登录页
  if (!token || !user) {
    return <LoginView onLogin={(u) => { setUser(u); setToken(authApi.getToken()); }} />;
  }

  const Active = TABS.find((t) => t.key === tab).view;

  function logout() {
    authApi.logout();
    setUser(null);
    setToken(null);
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>🛡 Governance Center <span className="sub">BottleSumo · agent-governance-v2</span></h1>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key}
                    className={tab === t.key ? 'tab active' : 'tab'}
                    onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
        </nav>
        <div className="userbox">
          <span className="role-badge">{ROLE_LABEL[user.role] || user.role}</span>
          <span className="uname">{user.username}</span>
          <button className="logout" onClick={logout}>退出</button>
        </div>
      </header>
      <main className="content"><Active /></main>
      <footer className="foot">S69 策略编辑器 · ARCH T0.3 可观测性 · ARCH-ROUND 2 RBAC · 治理可验证</footer>
    </div>
  );
}
