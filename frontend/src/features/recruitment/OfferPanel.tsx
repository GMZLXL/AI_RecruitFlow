import { useCallback, useState } from 'react';
import { Alert, Button, Descriptions, Form, Input, Select, message } from 'antd';
import { api, errorMessage, type Application } from '../../services/api';
import { useResource } from '../shared/useResource';
import { EmptyState, ErrorState, LoadState } from '../../components/RemoteState';
import { formatTime } from './presentation';
import { localTimestamp, asShanghaiTimestamp } from './dates';

type Fields = { status?: 'accepted' | 'declined'; at: string; reason: string };
export default function OfferPanel({ application, canWrite, changed }: { application: Application; canWrite: boolean; changed: () => void }) {
  const offer = useResource(useCallback((signal: AbortSignal) => api.offer(application.id, signal), [application.id]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm<Fields>();
  const save = async (value: Fields) => {
    setBusy(true); setError('');
    try {
      if (offer.data) await api.respondOffer(application.id, offer.data, { status: value.status!, responded_at: asShanghaiTimestamp(value.at), change_reason: value.reason }, key);
      else await api.createOffer(application, { sent_at: asShanghaiTimestamp(value.at), change_reason: value.reason }, key);
      changed(); message.success('Offer事实已登记；未发送消息，也未自动变更录用状态');
    } catch (cause) { setError(errorMessage(cause, 'Offer记录失败，请刷新核对版本')); }
    finally { setBusy(false); }
  };
  if (offer.loading) return <LoadState />;
  if (offer.error) return <ErrorState error={offer.error} retry={offer.reload} />;
  return <>
    <Alert type="info" showIcon message="这里登记已经发生的Offer事实，不发送Offer。接受与录用独立，拒绝不自动淘汰。" />
    {offer.data ? <Descriptions className="section-card" column={1} items={[
      { key: 'status', label: '反馈', children: ({ sent: '已发出 · 待反馈', accepted: '已接受', declined: '已拒绝' })[offer.data.status] },
      { key: 'sent', label: '发出时间', children: formatTime(offer.data.sent_at) },
      { key: 'response', label: '反馈时间', children: offer.data.responded_at ? formatTime(offer.data.responded_at) : '尚未反馈' },
    ]} /> : <EmptyState description="尚未登记Offer发出事实，旧录用记录不会推断为已接受" />}
    {canWrite && ((!offer.data && application.stage === 'offer') || offer.data?.status === 'sent') && <Form form={form} className="section-card compact-form" layout="vertical"
      initialValues={{ at: localTimestamp() }} onFinish={value => void save(value)} onValuesChange={() => setKey(crypto.randomUUID())}>
      {error && <Alert type="error" showIcon message={error} description="输入已保留，请核对时间或刷新版本后重试。" />}
      {offer.data && <Form.Item name="status" label="候选人明确反馈" rules={[{ required: true }]}><Select options={[{ value: 'accepted', label: '接受Offer' }, { value: 'declined', label: '拒绝Offer' }]} /></Form.Item>}
      <Form.Item name="at" label={offer.data ? '实际反馈时间（上海）' : '实际发出时间（上海）'} rules={[{ required: true }]}><Input type="datetime-local" step={1} /></Form.Item>
      <Form.Item name="reason" label="登记依据" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} maxLength={500} /></Form.Item>
      <Button type="primary" loading={busy} htmlType="submit">{offer.data ? '登记反馈' : '登记已发出'}</Button>
    </Form>}
  </>;
}
