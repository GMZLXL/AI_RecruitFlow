import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Layout, Menu, Select, Space, Spin, Tag, Typography } from 'antd';
import { api, errorMessage, type User } from '../services/api';
import Dashboard from '../pages/Dashboard';
import Candidates from '../pages/Candidates';
import AIInbox from '../pages/AIInbox';
import SyncCenter from '../pages/SyncCenter';
import FeaturePending from '../components/FeaturePending';
const { Header, Sider, Content } = Layout;
const { Text } = Typography;
export default function App() {
  const loc = useLocation(); const nav = useNavigate();
  const [identity, setIdentity] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [authError, setAuthError] = useState('');
  useEffect(() => { void Promise.all([api.me(), api.devUsers()]).then(([me, options]) => { setIdentity(me.user); setUsers(options); }).catch(error => setAuthError(errorMessage(error, '无法读取开发身份，请启动后端并完成迁移'))); }, []);
  const canWrite = identity?.role === 'HR' || identity?.role === 'ADMIN';
  const items = [
    {key:'/dashboard',label:'招聘工作台'}, {key:'/candidates',label:'候选人记录'},
    {key:'/ai-inbox',label:'AI消息录入'}, {key:'/tasks',label:'待办提醒'},
    {key:'/sync',label:'同步中心'}, {key:'/settings',label:'系统设置'},
  ].filter(item => identity?.role === 'ADMIN' || item.key !== '/sync');
  return <Layout className="app-shell">
    <Sider theme="light" width={218} breakpoint="lg" collapsedWidth={0}>
      <div className="brand">AI <strong>RecruitFlow</strong><small>招聘运营智能助手</small></div>
      <Menu mode="inline" selectedKeys={[loc.pathname]} items={items} onClick={({key})=>nav(key)} />
    </Sider>
    <Layout>
      <Header className="topbar"><Space wrap><Text strong>AI 招聘自动化</Text><Tag color="gold">MOCK · 开发模拟身份</Tag><Select aria-label="开发模拟身份" value={identity?.id} options={users.map(user=>({value:user.id,label:`${user.display_name} · ${user.role}`}))} style={{width:205}} onChange={api.selectDevUser} /></Space><Text type="secondary"><Link to="/settings">连接设置</Link></Text></Header>
      <Content className="app-content">{authError ? <Alert type="error" message={authError} action={<Button onClick={()=>{sessionStorage.removeItem('recruitflow.dev_user');window.location.reload();}}>恢复默认开发身份</Button>} /> : !identity ? <Spin tip="读取开发身份"><div style={{minHeight:200}} /></Spin> : <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} /><Route path="/dashboard" element={<Dashboard />} />
        <Route path="/candidates" element={<Candidates canWrite={canWrite} />} /><Route path="/ai-inbox" element={canWrite ? <AIInbox /> : <Alert type="warning" message="当前负责人身份仅有查看权限" />} />
        <Route path="/tasks" element={<FeaturePending title="待办提醒" />} />
        <Route path="/sync" element={identity.role === 'ADMIN' ? <SyncCenter /> : <Alert type="warning" message="仅管理员可以访问同步中心" />} /><Route path="/settings" element={<FeaturePending title="系统设置" />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>}</Content>
    </Layout>
  </Layout>;
}
