import React, { useState } from 'react';
import { authApi } from '../services/api.js';

// 登录页 (ARCH-ROUND 2 / GAP-3.1): 首次启动种子用户 admin/admin123
export default function LoginView({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const user = await authApi.login(username, password);
      onLogin(user);
    } catch (err) {
      setError(err.message.replace(/^4\d\d: /, '') || '登录失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h2>🛡 Governance Center</h2>
        <p className="sub">BottleSumo · 治理中枢（RBAC 已启用）</p>
        <input placeholder="用户名" value={username}
               onChange={(e) => setUsername(e.target.value)} autoFocus />
        <input type="password" placeholder="密码" value={password}
               onChange={(e) => setPassword(e.target.value)} />
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy || !username || !password}>
          {busy ? '登录中…' : '登录'}
        </button>
        <p className="hint">默认种子用户: admin / admin123（生产请立即改密并设置 GOV_AUTH_SECRET）</p>
      </form>
    </div>
  );
}
