import { lazy, Suspense, useCallback, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Drawer, Layout, Menu, Select, Space, Tag, Typography } from 'antd';
import { api } from '../services/api';
import { useResource } from '../features/shared/useResource';
import { ErrorState, LoadState } from '../components/RemoteState';
import AppErrorBoundary from '../components/AppErrorBoundary';
const Dashboard = lazy(() => import('../pages/Dashboard'));
const Candidates = lazy(() => import('../pages/Candidates'));
const ApplicationDetail = lazy(() => import('../pages/ApplicationDetail'));
const AIInbox = lazy(() => import('../pages/AIInbox'));
const Tasks = lazy(() => import('../pages/Tasks'));
const SyncCenter = lazy(() => import('../pages/SyncCenter'));
const Settings = lazy(() => import('../pages/Settings'));
const { Header, Sider, Content } = Layout;

export default function App() {
  const loc = useLocation(); const nav = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const auth = useResource(useCallback(async () => {
    const [identity, users] = await Promise.all([api.me(), api.devUsers()]);
    return { identity: identity.user, users };
  }, []));
  const identity = auth.data?.identity;
  const canWrite = identity?.role === 'HR' || identity?.role === 'ADMIN';
  const isAdmin = identity?.role === 'ADMIN';
  const items = [
    { key: '/dashboard', label: '招聘工作台' }, { key: '/candidates', label: '候选人与申请' },
    { key: '/ai-inbox', label: 'AI录入与审核' }, { key: '/tasks', label: '面试与待办' },
    { key: '/sync', label: '同步中心' }, { key: '/settings', label: '系统设置' },
  ].filter(item => isAdmin || item.key !== '/sync');
  const menu = <Menu mode="inline" selectedKeys={[loc.pathname.startsWith('/applications') ? '/candidates' : loc.pathname]} items={items}
    onClick={({ key }) => { nav(key); setMenuOpen(false); }} />;
  return <Layout className="app-shell">
    <Sider theme="light" width={220} className="desktop-sidebar"><div className="brand">AI <strong>RecruitFlow</strong><small>招聘运营智能助手</small></div>{menu}</Sider>
    <Layout className="app-main">
      <Header className="topbar"><Space wrap>
        <Button className="mobile-nav-toggle" onClick={() => setMenuOpen(true)} aria-label="打开导航">导航</Button>
        <Typography.Text strong>AI 招聘自动化</Typography.Text><Tag color="gold">MOCK · 开发模拟身份</Tag>
      </Space><Space wrap>
        <Select aria-label="开发模拟身份" value={identity?.id} className="identity-select" loading={auth.loading}
          options={auth.data?.users.map(user => ({ value: user.id, label: `${user.display_name} · ${user.role}` }))} onChange={api.selectDevUser} />
        <Link to="/settings">连接设置</Link>
      </Space></Header>
      <Content className="app-content">
        {auth.error ? <><ErrorState error={auth.error} retry={auth.reload} /><Button className="section-card" onClick={() => { sessionStorage.removeItem('recruitflow.dev_user'); window.location.reload(); }}>恢复默认开发身份</Button></>
          : !identity ? <LoadState /> : <AppErrorBoundary key={loc.pathname}><Suspense fallback={<LoadState />}><Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} /><Route path="/dashboard" element={<Dashboard />} />
            <Route path="/candidates" element={<Candidates canWrite={canWrite} />} /><Route path="/applications" element={<Navigate to="/candidates" replace />} />
            <Route path="/applications/:id" element={<ApplicationDetail identity={identity} />} />
            <Route path="/ai-inbox" element={canWrite ? <AIInbox /> : <Alert type="warning" message="负责人为只读身份，AI审核需HR或管理员处理" />} />
            <Route path="/tasks" element={<Tasks canWrite={canWrite} />} /><Route path="/sync" element={isAdmin ? <SyncCenter /> : <Alert type="warning" message="仅管理员可以访问同步中心" />} />
            <Route path="/settings" element={<Settings identity={identity} />} /><Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes></Suspense></AppErrorBoundary>}
      </Content>
    </Layout>
    <Drawer title="招聘工作导航" placement="left" width="min(320px, 100vw)" open={menuOpen} onClose={() => setMenuOpen(false)}>{menu}</Drawer>
  </Layout>;
}
