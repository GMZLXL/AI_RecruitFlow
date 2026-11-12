import { useCallback, useState } from 'react';
import { Alert, Button, Card, Form, Input, Modal, Table, Tag } from 'antd';
import { api, errorMessage, type Notification } from '../../services/api';
import { useResource } from '../shared/useResource';
import { ErrorState } from '../../components/RemoteState';
import { formatTime } from '../recruitment/presentation';

const labels: Record<Notification['status'], string> = { pending: '排队中', processing: '发送处理中', mock_sent: '模拟发送', accepted: '平台已接受', blocked: '待配置', failed: '明确失败', uncertain: '结果不明，需核实', cancelled: '事实或权限变更，已取消' };
export default function DeliveryQueue({ admin = false }: { admin?: boolean }) {
  const [page, setPage] = useState(1);
  const rows = useResource(useCallback((signal: AbortSignal) => api.notifications(page, signal), [page]));
  const [target, setTarget] = useState<Notification>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm<{ reason: string }>();
  return <Card title="通知记录" className="section-card" extra={<Button onClick={rows.reload}>刷新通知</Button>}>
    <p className="chart-note">模拟发送不会联系企业微信；平台已接受只代表发送接口返回成功，不代表成员收到或已读。结果不明需管理员核实，不能直接重发。</p>
    {rows.error && <ErrorState error={rows.error} retry={rows.reload} />}
    <Table<Notification> rowKey="id" loading={rows.loading} dataSource={rows.data?.data ?? []} scroll={{ x: 900 }} locale={{ emptyText: '暂无通知；提醒默认关闭，可由管理员在系统设置启用' }}
      pagination={{ current: page, pageSize: 8, total: rows.data?.pagination.total ?? 0, showSizeChanger: false, onChange: setPage }} columns={[
        { title: '状态', dataIndex: 'status', width: 180, render: (value: Notification['status']) => <Tag color={value === 'mock_sent' ? 'blue' : value === 'accepted' ? 'green' : value === 'uncertain' || value === 'failed' ? 'red' : 'default'}>{labels[value]}</Tag> },
        { title: '内容', dataIndex: 'text', width: 300 }, { title: '接收人', dataIndex: 'recipient_name', width: 140 },
        { title: '创建时间', dataIndex: 'created_at', width: 180, render: formatTime },
        { title: '错误 / 尝试', width: 190, render: (_, row) => `${row.last_error ?? '无'} / ${row.attempts}` },
        ...(admin ? [{ title: '操作', width: 110, render: (_: unknown, row: Notification) => ['failed', 'blocked'].includes(row.status) ? <Button onClick={() => { setTarget(row); setError(''); form.resetFields(); setKey(crypto.randomUUID()); }}>重试通知</Button> : null }] : []),
      ]} />
    <Modal title="重试明确失败的通知" open={!!target} onCancel={() => { if (!busy) setTarget(undefined); }} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onValuesChange={() => setKey(crypto.randomUUID())} onFinish={async ({ reason }) => {
        if (!target) return; setBusy(true); setError('');
        try { await api.retryNotification(target, reason, key); setTarget(undefined); rows.reload(); }
        catch (cause) { setError(errorMessage(cause, '重试失败；版本冲突时请关闭并刷新通知')); }
        finally { setBusy(false); }
      }}>
        {error && <Alert type="error" message={error} />}
        <Form.Item name="reason" label="重试依据" rules={[{ required: true, whitespace: true }]}><Input.TextArea maxLength={300} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>确认重试</Button>
      </Form>
    </Modal>
  </Card>;
}
