import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Col, Form, Input, Layout, Menu, Row, Select, Space, Spin, Statistic, Table, Tag, Typography, message } from 'antd';
import ReactECharts from 'echarts-for-react';
import { api, errorMessage, type Application, type ApplicationCreate, type DashboardData, type IngestResult, type Stage, type SyncJob, type User } from './api';
const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const STAGES: Record<Stage, string> = { applied: '新申请', screening: '简历筛选', interview_1: '一面', interview_2: '二面', offer: 'Offer阶段', hired: '录用', rejected: '淘汰/结束', withdrawn: '主动退出' };
const stageLabel = (stage: string) => STAGES[stage as Stage] ?? stage;
const formatTime = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
const NEXT_STAGE: Partial<Record<Stage, Stage>> = { applied: 'screening', screening: 'interview_1', interview_1: 'interview_2', interview_2: 'offer' };

function PageHead({ title, desc }: {title: string; desc?: string}) {
  return <div className="page-head"><Title level={3} style={{ margin: 0 }}>{title}</Title>{desc && <Text type="secondary">{desc}</Text>}</div>;
}

function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => { try { setError(''); setData(await api.dashboard()); } catch { setError('无法连接后端，请确认 FastAPI 已启动。'); } }, []);
  useEffect(() => { void load(); }, [load]);
  const chart = useMemo(() => ({
    tooltip: { trigger: 'axis' }, grid: { left: 40, right: 20, top: 25, bottom: 40 },
    xAxis: { type: 'category', data: Object.keys(data?.by_stage || {}).map(stageLabel) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', barWidth: 45, data: Object.values(data?.by_stage || {}), itemStyle: { color: '#1677ff', borderRadius: [6, 6, 0, 0] } }]
  }), [data]);
  return <>
    <PageHead title="招聘工作台" desc="招聘数据直接来自本地数据库，演示环境不连接真实腾讯文档。" />
    {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} />}
    <Row gutter={[16,16]}>
      <Col xs={24} md={8}><Card><Statistic title="招聘申请总数" value={data?.new_applications ?? '—'} /></Card></Col>
      <Col xs={24} md={8}><Card><Statistic title="等待模拟同步" value={data?.pending_sync ?? '—'} /></Card></Col>
      <Col xs={24} md={8}><Card><Statistic title="运行环境" value="Mock" valueStyle={{fontSize: 23}} /></Card></Col>
    </Row>
    <Card className="section-card" title="招聘阶段分布" extra={<Button onClick={() => void load()}>刷新</Button>}>
      {!data || Object.keys(data.by_stage).length === 0 ? <Text type="secondary">暂无申请数据，可在“候选人记录”或“AI录入”新增演示记录。</Text> : <ReactECharts option={chart} style={{height:320}} />}
    </Card>
  </>;
}

function Candidates({ canWrite }: { canWrite: boolean }) {
  const [rows, setRows] = useState<Application[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [form] = Form.useForm<ApplicationCreate>();
  const refresh = useCallback(async () => { setLoading(true); try { const result = await api.applications(page); setRows(result.data); setTotal(result.pagination.total); } catch { message.error('无法获取招聘申请'); } finally { setLoading(false); } }, [page]);
  useEffect(() => { void refresh(); }, [refresh]);
  const submit = async (v: ApplicationCreate) => {
    setSaving(true);
    try { await api.addApplication({ ...v, application_code: v.application_code?.trim() || undefined }); form.resetFields(); message.success('已写入本地数据库，腾讯文档尚未真实同步'); if (page === 1) await refresh(); else setPage(1); }
    catch (error) { message.error(errorMessage(error, '新增失败，请检查后端运行状态')); }
    finally { setSaving(false); }
  };
  const advance = async (row: Application) => {
    const target = NEXT_STAGE[row.stage];
    if (!target) return;
    setSaving(true);
    try { await api.advance(row, target); await refresh(); message.success('阶段已更新并写入审计，等待模拟同步'); }
    catch (error) { message.error(errorMessage(error, '阶段更新失败，请刷新后重试')); }
    finally { setSaving(false); }
  };
  return <>
    <PageHead title="候选人记录" desc="申请按后端授权范围显示。HR新增时须使用已配置的岗位名称；同一候选人多岗申请可通过ID接口创建。" />
    {canWrite && <Card title="新增演示记录">
      <Form form={form} layout="inline" onFinish={(v) => void submit(v)}>
        <Form.Item name="candidate_name" label="候选人" rules={[{required:true,whitespace:true,message:'请填写姓名'}]}><Input maxLength={100} placeholder="虚构候选人" /></Form.Item>
        <Form.Item name="position_title" label="岗位" rules={[{required:true,whitespace:true,message:'请填写岗位'}]}><Input maxLength={120} placeholder="数据分析岗" /></Form.Item>
        <Form.Item name="application_code" label="申请编号"><Input maxLength={40} placeholder="如 A10001（选填）" /></Form.Item>
        <Form.Item><Button type="primary" htmlType="submit" loading={saving}>新增</Button></Form.Item>
      </Form>
    </Card>}
    <Card className="section-card" title="招聘申请" extra={<Button onClick={() => void refresh()}>刷新</Button>}>
      <Table loading={loading} rowKey="id" dataSource={rows} pagination={{current:page,pageSize:8,total,showSizeChanger:false,onChange:setPage}} scroll={{x:720}} columns={[
        {title:'申请编号',dataIndex:'application_code',width:140}, {title:'候选人',dataIndex:'candidate_name',width:120},
        {title:'岗位',dataIndex:'position_title',width:170}, {title:'当前阶段',dataIndex:'stage',render:(s:Stage)=><Tag color="blue">{STAGES[s]}</Tag>},
        {title:'版本',dataIndex:'version',width:70}, {title:'更新时间（上海）',dataIndex:'updated_at',render:formatTime,width:190},
        {title:'人工推进',key:'advance',width:150,render:(_:unknown,row:Application)=>canWrite && NEXT_STAGE[row.stage] ? <Button size="small" loading={saving} onClick={()=>void advance(row)}>推进至{STAGES[NEXT_STAGE[row.stage]!]}</Button> : '—'}
      ]} />
    </Card>
  </>;
}

function AIInbox() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const submit = async () => {
    setBusy(true); setResult(null);
    try { setResult(await api.ingest(text)); message.info('Mock 解析结束；真实 DeepSeek 接入见开发任务 S2'); }
    catch { message.error('处理失败，请检查后端运行状态'); }
    finally { setBusy(false); }
  };
  return <>
    <PageHead title="AI 消息录入" desc="支持明确新增；阶段更新须先人工推进到一面，再输入申请编号 + 一面通过。完整Parser与审核在S2实施。" />
    <Row gutter={[16,16]}>
      <Col xs={24} lg={13}><Card title="粘贴招聘业务消息"><Input.TextArea rows={7} maxLength={2000} showCount placeholder="例如：新增张三应聘数据分析岗" value={text} onChange={e=>setText(e.target.value)} /><Button block type="primary" loading={busy} disabled={!text.trim()} style={{marginTop:22}} onClick={() => void submit()}>解析并处理</Button></Card></Col>
      <Col xs={24} lg={11}><Card title="AI 处理结果" style={{minHeight:285}}>{!result ? <Text type="secondary">提交后在此展示系统处理状态。</Text> : <>
        <Alert showIcon type={result.status==='applied'?'success':result.status==='needs_confirmation'?'warning':'info'} message={result.status==='applied'?'本地业务记录处理成功':result.status==='needs_confirmation'?'需要人工确认':result.status==='duplicate'?'重复事件':'处理结果'} description={result.reason || result.intent || ''} />
        {result.application && <Paragraph style={{marginTop:12}}>申请：{result.application.application_code}<br/>候选人：{result.application.candidate_name}<br/>当前阶段：{STAGES[result.application.stage]}<br/>腾讯文档：<Tag>待模拟同步</Tag></Paragraph>}
        {result.status==='needs_confirmation' && <Text type="secondary">完整的待确认队列、候选人匹配和编辑界面将在 Codex S2/S4 完成。</Text>}
      </>}</Card></Col>
    </Row>
    <Alert className="section-card" type="warning" showIcon message="本页面是本地 Mock 演示，不会调用 DeepSeek，也不会向腾讯文档或企业微信发送任何数据。" />
  </>;
}

function SyncCenter() {
  const [jobs, setJobs] = useState<SyncJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const load = useCallback(async () => { try { const result = await api.syncJobs(page); setJobs(result.data); setTotal(result.pagination.total); } catch { message.error('同步任务获取失败'); } }, [page]);
  useEffect(() => { void load(); }, [load]);
  const run = async () => { setBusy(true); try { const r=await api.runMockSync(); message.success(`${r.processed}个任务完成模拟同步（未写入腾讯文档）`); await load(); } catch { message.error('模拟同步失败'); } finally { setBusy(false); } };
  return <>
    <PageHead title="同步中心" desc="真实集成依赖腾讯文档 Token、MCP Schema 和智能表格授权；当前演示严格区分模拟与真实状态。" />
    <Alert type="warning" showIcon message="当前为 Mock SmartSheetAdapter" description="点击“执行模拟同步”仅生成 MOCK- 标识，不代表腾讯文档已写入。" />
    <Card className="section-card" title="同步任务" extra={<Space><Button onClick={() => void load()}>刷新</Button><Button type="primary" loading={busy} onClick={() => void run()}>执行模拟同步</Button></Space>}>
      <Table rowKey="id" dataSource={jobs} scroll={{x:650}} pagination={{current:page,pageSize:8,total,showSizeChanger:false,onChange:setPage}} columns={[
        {title:'任务ID',dataIndex:'id'}, {title:'申请ID',dataIndex:'application_id'},
        {title:'版本',dataIndex:'version'}, {title:'状态',dataIndex:'status',render:(s:string)=><Tag color={s==='mock_synced'?'green':'orange'}>{s==='mock_synced'?'模拟已同步':s}</Tag>},
        {title:'远端模拟ID',dataIndex:'remote_record_id',render:(s:string|null)=>s || '—'}, {title:'尝试次数',dataIndex:'attempts'}
      ]}/>
    </Card>
  </>;
}

function Placeholder({ title }: {title:string}) { return <><PageHead title={title} desc="属于完整 MVP 设计范围；请用 docs/02 与 codex/PHASE_TASKS.md 指导 Codex 继续开发。"/><Card><Text type="secondary">当前 Starter 只提供基础演示。完整身份权限、面试管理、人工审核、企微回调与生产部署尚未实现。</Text></Card></>; }

function Shell() {
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
        <Route path="/tasks" element={<Placeholder title="待办提醒" />} />
        <Route path="/sync" element={identity.role === 'ADMIN' ? <SyncCenter /> : <Alert type="warning" message="仅管理员可以访问同步中心" />} /><Route path="/settings" element={<Placeholder title="系统设置" />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>}</Content>
    </Layout>
  </Layout>;
}
export default function App() { return <Shell />; }
