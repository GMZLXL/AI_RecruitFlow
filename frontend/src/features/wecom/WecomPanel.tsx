import { useCallback, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, InputNumber, Select, Space, Steps, Switch, Table, Tabs } from 'antd';
import { Link } from 'react-router-dom';
import { api, errorMessage, type ReminderPolicyUpdate } from '../../services/api';
import { useResource } from '../shared/useResource';
import { ErrorState, LoadState } from '../../components/RemoteState';
import DeliveryQueue from './DeliveryQueue';

const states = { mock_only: '模拟模式', disabled: '未启用', blocked_by_credentials: '凭证缺失', configured_not_verified: '已配置，尚未联调验证' };
const inboxStates = { pending: '已接收，等待解析', processing: '后台解析中', completed: '已处理，请查看AI结果', failed: '处理失败' };

function BindingForm() {
  const [page, setPage] = useState(1);
  const users = useResource(useCallback((signal: AbortSignal) => api.wecomUsers(page, signal), [page]), { keepPreviousData: true });
  const [form] = Form.useForm<{ user_id: string; external_userid?: string; reason: string }>();
  const selected = Form.useWatch('user_id', form);
  const selectedUser = users.data?.data.find(row => row.id === selected);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  return <>
    {users.error && <ErrorState error={users.error} retry={users.reload} />}
    <Table rowKey="id" loading={users.loading} dataSource={users.data?.data ?? []} scroll={{ x: 550 }} pagination={{ current: page, pageSize: 8, total: users.data?.pagination.total ?? 0, onChange: value => { setPage(value); form.setFieldValue('user_id', undefined); setSuccess(''); }, showSizeChanger: false }} columns={[
      { title: '内部用户', dataIndex: 'display_name' }, { title: '角色', dataIndex: 'role' }, { title: '企微UserID', dataIndex: 'external_wecom_userid', render: value => value ?? '未绑定' },
    ]} />
    <Form name="wecom-binding" form={form} className="compact-form" layout="vertical" onValuesChange={() => { setKey(crypto.randomUUID()); setSuccess(''); }} onFinish={async value => {
      const row = users.data?.data.find(user => user.id === value.user_id);
      if (!row) { setError('所选用户不在当前页，请重新选择内部用户'); return; }
      setBusy(true); setError(''); setSuccess('');
      try { const saved = await api.bindWecomUser(row, { external_userid: value.external_userid?.trim() || null, change_reason: value.reason }, key); setSuccess(`${saved.display_name}的企微绑定已保存（版本${saved.version}）`); form.setFieldValue('reason', ''); setKey(crypto.randomUUID()); users.reload(); }
      catch (cause) { setError(errorMessage(cause, '绑定失败，请核对用户与版本')); }
      finally { setBusy(false); }
    }}>
      {error && <Alert type="error" message={error} />}
      {success && <div role="status"><Alert type="success" showIcon message={success} /></div>}
      <Button aria-label="刷新用户版本，保留草稿" className="section-card" loading={users.loading} disabled={busy} onClick={() => { setError(''); setSuccess(''); users.reload(); }}>刷新用户版本，保留草稿</Button>
      {selectedUser && <p>最新已保存：{selectedUser.display_name} · {selectedUser.external_wecom_userid ?? '未绑定'}（版本{selectedUser.version}）。请与下方草稿核对后保存。</p>}
      <Form.Item name="user_id" label="内部用户（当前页）" rules={[{ required: true }]}><Select options={users.data?.data.map(row => ({ value: row.id, label: row.display_name }))} /></Form.Item>
      <Form.Item name="external_userid" label="企微成员UserID（留空解除绑定）"><Input maxLength={150} autoComplete="off" /></Form.Item>
      <Form.Item name="reason" label="绑定变更依据" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={busy} disabled={users.loading || !!users.error}>保存用户绑定</Button>
    </Form>
  </>;
}

function ReminderForm() {
  const policy = useResource(useCallback((signal: AbortSignal) => api.reminderPolicy(signal), []), { keepPreviousData: true });
  const [form] = Form.useForm<ReminderPolicyUpdate>();
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  if (!policy.data) return policy.loading ? <LoadState /> : <ErrorState error={policy.error} retry={policy.reload} />;
  return <Form name="wecom-reminders" form={form} className="compact-form" layout="vertical" initialValues={policy.data} onValuesChange={() => { setKey(crypto.randomUUID()); setSuccess(''); }} onFinish={async value => {
    setBusy(true); setError(''); setSuccess('');
    try { const saved = await api.updateReminderPolicy(policy.data!, value, key); form.setFieldsValue({ ...saved, change_reason: '' }); setSuccess(`提醒规则已保存，当前为${saved.enabled ? '启用' : '关闭'}（版本${saved.version}）`); policy.reload(); setKey(crypto.randomUUID()); }
    catch (cause) { setError(errorMessage(cause, '规则保存失败；版本冲突时刷新后重新核对')); }
    finally { setBusy(false); }
  }}>
    <p>后台约每30秒按实际面试、超时反馈、停滞申请和同步故障生成提醒；同一事实只提醒一次。发送前再次核对记录和权限，业务变化后取消过期提醒。</p>
    <Button aria-label="刷新规则版本，保留草稿" loading={policy.loading} disabled={busy} onClick={() => { setError(''); setSuccess(''); policy.reload(); }}>刷新规则版本，保留草稿</Button>
    <p>最新已保存：{policy.data.enabled ? '启用' : '关闭'}，面试提前{policy.data.interview_hours}小时、反馈{policy.data.feedback_hours}小时、停滞{policy.data.stalled_days}天（版本{policy.data.version}）。刷新保留草稿，请核对后保存。</p>
    {policy.error && <ErrorState error={policy.error} retry={policy.reload} />}
    {error && <Alert type="error" message={error} />}
    {success && <div role="status"><Alert type="success" showIcon message={success} /></div>}
    <Form.Item name="enabled" label="启用自动提醒" valuePropName="checked"><Switch /></Form.Item>
    <Form.Item name="interview_hours" label="面试提前（小时）" rules={[{ required: true }]}><InputNumber min={1} max={168} /></Form.Item>
    <Form.Item name="feedback_hours" label="面试后未反馈（小时）" rules={[{ required: true }]}><InputNumber min={1} max={720} /></Form.Item>
    <Form.Item name="stalled_days" label="申请未更新（天）" rules={[{ required: true }]}><InputNumber min={1} max={365} /></Form.Item>
    <Form.Item name="change_reason" label="提醒变更依据" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
    <Button type="primary" htmlType="submit" loading={busy} disabled={policy.loading || !!policy.error}>保存提醒规则</Button>
  </Form>;
}

function MockForm({ enabled }: { enabled: boolean }) {
  const inbox = useResource(useCallback((signal: AbortSignal) => api.wecomInbox(1, signal), []));
  const [form] = Form.useForm<{ text: string; message_id: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [accepted, setAccepted] = useState(false);
  return <>
    <Alert type="info" showIcon message="模拟主动投稿：以当前用户权限进入AI处理流程，不访问企业微信。相同消息ID只处理一次。" />
    <Form form={form} className="compact-form" layout="vertical" initialValues={{ message_id: crypto.randomUUID() }} onValuesChange={() => { setKey(crypto.randomUUID()); setAccepted(false); }} onFinish={async value => {
      setBusy(true); setError('');
      try { await api.mockWecom(value, key); setAccepted(true); inbox.reload(); }
      catch (cause) { setError(errorMessage(cause, '投稿失败，请保留原消息ID重试')); }
      finally { setBusy(false); }
    }}>
      {error && <Alert type="error" message={error} />}{accepted && <Alert type="success" message={<>已接收，等待后台处理。<Link to="/ai-inbox">查看AI录入与审核</Link>，或刷新下方记录。</>} />}
      <Form.Item name="message_id" label="模拟消息ID" rules={[{ required: true, whitespace: true }]}><Input maxLength={150} /></Form.Item>
      <Form.Item name="text" label="招聘消息" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} maxLength={2000} placeholder="例如：A10001进入一面（仅使用虚构记录）" /></Form.Item>
      <Space wrap><Button htmlType="submit" type="primary" loading={busy} disabled={!enabled}>提交模拟消息</Button><Button onClick={() => { form.setFieldValue('message_id', crypto.randomUUID()); setKey(crypto.randomUUID()); setAccepted(false); }}>开始新消息</Button><Button onClick={inbox.reload}>刷新接收记录</Button></Space>
    </Form>
    {inbox.error && <ErrorState error={inbox.error} retry={inbox.reload} />}
    <p className="chart-note">最近8条接收任务；失败任务可由管理员通过接收重试API恢复，步骤见接入手册。</p>
    <Table rowKey="id" loading={inbox.loading} dataSource={inbox.data?.data ?? []} pagination={false} scroll={{ x: 600 }} locale={{ emptyText: '尚无投稿' }} columns={[
      { title: '来源', dataIndex: 'provider', render: value => value === 'mock' ? '模拟' : '真实回调' },
      { title: '状态', dataIndex: 'status', render: (value: keyof typeof inboxStates) => inboxStates[value] },
      { title: '错误', dataIndex: 'last_error', render: value => value ?? '无' },
    ]} />
  </>;
}

export default function WecomPanel() {
  const connection = useResource(useCallback((signal: AbortSignal) => api.wecomStatus(signal), []), { keepPreviousData: true });
  return <>
    <Card className="section-card" title="企业微信与提醒" extra={<Button aria-label="刷新企微状态" loading={connection.loading} onClick={connection.reload}>刷新企微状态</Button>}>
      {connection.error && <ErrorState error={connection.error} retry={connection.reload} />}
      {connection.loading && !connection.data ? <LoadState /> : connection.data && <>
        <Descriptions column={{ xs: 1, md: 2 }} items={[
          { key: 'receive', label: '接收', children: states[connection.data.callback] }, { key: 'send', label: '发送', children: states[connection.data.sending] },
          { key: 'worker', label: '后台任务', children: connection.data.worker_enabled ? '已启用' : '已关闭，队列暂不处理' },
        ]} />
        <Alert type="warning" showIcon message="只接收HR主动发给自建应用的消息。普通群机器人不能监听群聊；已配置仍不代表真实联调通过。" />
        <Tabs items={[
          { key: 'guide', label: '接入与用户绑定', children: <>
            <Steps direction="vertical" size="small" items={[
              { title: '管理员创建自建应用', description: '在企微管理后台设置应用可见范围，取得CorpID、AgentID、Secret。' },
              { title: '在服务端配置回调', description: `公开HTTPS地址 + ${connection.data.callback_path}；Token和EncodingAESKey只写服务端环境，页面不接收密钥。` },
              { title: '绑定用户后授权测试', description: '成员UserID绑定到现有HR，核对权限；再执行URL校验、投稿与通知实测。参数及步骤见仓库docs/08接入手册。' },
            ]} /><BindingForm />
          </> },
          { key: 'reminders', label: '提醒规则', children: <ReminderForm /> },
          { key: 'mock', label: '模拟投稿', children: <MockForm enabled={connection.data.provider === 'mock'} /> },
        ]} />
      </>}
    </Card>
    <DeliveryQueue admin />
  </>;
}
