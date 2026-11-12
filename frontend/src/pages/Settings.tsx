import { useCallback, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, InputNumber, Select, Table, Tag, message } from 'antd';
import { api, errorMessage, type PositionCreate, type Position, type User } from '../services/api';
import { useResource } from '../features/shared/useResource';
import { ErrorState, LoadState } from '../components/RemoteState';
import PageHead from '../components/PageHead';
import { STAGES } from '../features/recruitment/presentation';
import WecomPanel from '../features/wecom/WecomPanel';

export default function Settings({ identity }: { identity: User }) {
  const admin = identity.role === 'ADMIN';
  const [page, setPage] = useState(1);
  const policy = useResource(useCallback((signal: AbortSignal) => api.policy(signal), []));
  const positions = useResource(useCallback((signal: AbortSignal) => api.positions(page, signal), [page]));
  const options = useResource(useCallback((signal: AbortSignal) => api.options('', signal), []));
  const connections = useResource(useCallback((signal: AbortSignal) => admin ? api.integrations(signal) : Promise.resolve(null), [admin]));
  const [form] = Form.useForm<PositionCreate>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const save = async (value: PositionCreate) => {
    const owner = options.data?.owners.find(row => row.id === value.owner_user_id);
    if (!owner) return;
    setBusy(true); setError('');
    try { await api.createPosition({ ...value, department: owner.department }, key); form.resetFields(); setKey(crypto.randomUUID()); positions.reload(); options.reload(); message.success('岗位已创建'); }
    catch (cause) { setError(errorMessage(cause, '岗位创建失败，请重试')); }
    finally { setBusy(false); }
  };
  return <><PageHead title="系统设置" desc="查看权限、岗位、阶段和连接状态。凭证只在服务端配置，页面不接收或回显密钥。" />
    <Card title="当前权限与业务规则">
      <Descriptions column={{ xs: 1, md: 2 }} items={[
        { key: 'user', label: '当前身份', children: `${identity.display_name} · ${identity.role}` },
        { key: 'scope', label: '数据范围', children: admin ? '全局业务与同步管理' : identity.role === 'HR' ? '本人负责申请，可录入和审核' : '所属部门进度，只读' },
        { key: 'privacy', label: '敏感字段', children: '本版本不采集或返回联系方式；所有接口由后端授权' },
        { key: 'reminder', label: '待办停滞阈值', children: policy.data ? `${policy.data.stalled_days}天未更新；自动提醒由管理员单独配置` : '读取中' },
      ]} />
      {policy.error && <ErrorState error={policy.error} retry={policy.reload} />}
      {policy.data && <p className="section-card">正常推进：{Object.values(STAGES).slice(0, 6).join(' → ')}。可人工记录淘汰或退出；终态逆转需审核。Offer接受和录用独立记录。</p>}
    </Card>
    {admin && <Card className="section-card" title="连接状态" extra={<Button onClick={connections.reload}>刷新配置状态</Button>}>
      {connections.error ? <ErrorState error={connections.error} retry={connections.reload} /> : connections.loading ? <LoadState /> : connections.data && <>
        <Descriptions column={{ xs: 1, md: 2 }} items={[
          { key: 'parser', label: 'AI解析', children: `${connections.data.parser_provider === 'mock' ? 'Mock规则' : 'DeepSeek'} · ${connections.data.deepseek}` },
          { key: 'sheet', label: '腾讯文档', children: connections.data.tencent_docs === 'blocked_by_credentials' ? '缺少Token，真实接入阻塞' : '工具Schema与字段映射待验证' },
          { key: 'mode', label: '当前投影', children: connections.data.sync_provider === 'mock' ? '本机Mock智能表格' : '腾讯适配器（尚未验证，写入阻断）' },
          { key: 'wecom', label: '企业微信', children: connections.data.wecom === 'mock_only' ? '模拟接入，详情见下方企微设置' : '独立配置状态，尚未完成真实联调' },
        ]} /><Alert type="warning" showIcon message="刷新只读取配置状态，不代表真实连通性验证通过。尚无经验证的腾讯字段映射；本页面不编造字段ID。" />
      </>}
    </Card>}
    {admin && <WecomPanel />}
    <Card className="section-card" title="岗位字典" extra={<Button onClick={positions.reload}>刷新岗位</Button>}>
      {positions.error && <ErrorState error={positions.error} retry={positions.reload} />}
      <Table<Position> rowKey="id" loading={positions.loading} dataSource={positions.data?.data ?? []} scroll={{ x: 650 }}
        pagination={{ current: page, pageSize: 8, total: positions.data?.pagination.total ?? 0, showSizeChanger: false, onChange: setPage }} columns={[
          { title: '岗位', dataIndex: 'title' }, { title: '部门', dataIndex: 'department' }, { title: '编制', dataIndex: 'target_headcount' },
          { title: '状态', dataIndex: 'active', render: value => <Tag>{value ? '启用' : '停用'}</Tag> },
        ]} />
      {admin && <Form form={form} className="compact-form section-card" layout="vertical" onFinish={value => void save(value)} onValuesChange={() => setKey(crypto.randomUUID())}>
        <h3>新增岗位</h3>{error && <Alert type="error" message={error} />}
        <Form.Item name="title" label="岗位名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="owner_user_id" label="负责人（部门自动匹配）" rules={[{ required: true }]}><Select options={options.data?.owners.map(row => ({ value: row.id, label: `${row.display_name} · ${row.department}` }))} /></Form.Item>
        <Form.Item name="target_headcount" label="招聘编制" initialValue={1} rules={[{ required: true }]}><InputNumber min={0} max={10000} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>创建岗位</Button>
      </Form>}
    </Card>
  </>;
}
