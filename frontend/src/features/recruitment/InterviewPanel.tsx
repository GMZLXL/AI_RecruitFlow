import { useCallback, useState } from 'react';
import { Alert, Button, Drawer, Form, Input, InputNumber, Select, Table, message } from 'antd';
import { api, errorMessage, type Application, type Interview, type InterviewCreate } from '../../services/api';
import { useResource } from '../shared/useResource';
import { ErrorState } from '../../components/RemoteState';
import { formatTime } from './presentation';
import { asShanghaiTimestamp } from './dates';

type Fields = InterviewCreate & { result?: 'passed' | 'failed' | 'cancelled'; change_reason?: string };
export default function InterviewPanel({ application, canWrite, changed }: { application: Application; canWrite: boolean; changed: () => void }) {
  const [page, setPage] = useState(1);
  const data = useResource(useCallback((signal: AbortSignal) => api.interviews(application.id, page, signal), [application.id, page]));
  const [editing, setEditing] = useState<Interview | 'new' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm<Fields>();
  const open = (row: Interview | 'new') => { form.resetFields(); setEditing(row); setError(''); setKey(crypto.randomUUID()); };
  const save = async (value: Fields) => {
    if (!editing) return;
    setBusy(true); setError('');
    try {
      if (editing === 'new') await api.createInterview(application, { round: value.round, interviewer: value.interviewer, scheduled_at: asShanghaiTimestamp(value.scheduled_at) }, key);
      else await api.updateInterview(editing, { result: value.result, status: value.result === 'cancelled' ? 'cancelled' : 'completed', change_reason: value.change_reason! }, key);
      setEditing(null); changed(); message.success('面试记录已保存，申请阶段不会因反馈自动改变');
    } catch (cause) { setError(errorMessage(cause, '保存失败，请刷新版本后重试')); }
    finally { setBusy(false); }
  };
  return <>
    {data.error && <ErrorState error={data.error} retry={data.reload} />}
    {canWrite && ['interview_1', 'interview_2'].includes(application.stage) && <Button type="primary" onClick={() => open('new')}>安排面试</Button>}
    <Table<Interview> rowKey="id" loading={data.loading} dataSource={data.data?.data ?? []} scroll={{ x: 700 }} locale={{ emptyText: '暂无面试记录' }}
      pagination={{ current: page, pageSize: 8, total: data.data?.pagination.total ?? 0, onChange: setPage, showSizeChanger: false }} columns={[
        { title: '轮次', dataIndex: 'round', render: value => `第${value}轮` },
        { title: '计划时间（上海）', dataIndex: 'scheduled_at', render: value => value ? formatTime(value) : '原计划未知' },
        { title: '面试官', dataIndex: 'interviewer', render: value => value || '未知' },
        { title: '状态', dataIndex: 'status', render: value => ({ scheduled: '已安排', completed: '已完成', cancelled: '已取消' })[value as Interview['status']] },
        { title: '结果', dataIndex: 'result', render: value => ({ pending: '待反馈', passed: '通过', failed: '未通过', cancelled: '取消' })[value as Interview['result']] },
        { title: '操作', key: 'actions', render: (_, row) => canWrite && row.status === 'scheduled' ? <Button onClick={() => open(row)}>记录反馈</Button> : '—' },
      ]} />
    <Drawer title={editing === 'new' ? '安排面试' : '记录面试反馈'} width="min(500px, 100vw)" open={!!editing} onClose={() => !busy && setEditing(null)}>
      {error && <Alert type="error" showIcon message={error} description="输入已保留，请核对当前记录版本。" />}
      <Form form={form} layout="vertical" onFinish={value => void save(value)} onValuesChange={() => setKey(crypto.randomUUID())}>
        {editing === 'new' ? <><Form.Item name="round" label="面试轮次" initialValue={application.stage === 'interview_2' ? 2 : 1} rules={[{ required: true }]}><InputNumber min={1} max={30} /></Form.Item>
          <Form.Item name="scheduled_at" label="计划时间（上海）" rules={[{ required: true }]}><Input type="datetime-local" step={1} /></Form.Item>
          <Form.Item name="interviewer" label="面试官" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item></>
          : <><Form.Item name="result" label="本轮反馈" rules={[{ required: true }]}><Select options={[{ value: 'passed', label: '通过' }, { value: 'failed', label: '未通过' }, { value: 'cancelled', label: '取消面试' }]} /></Form.Item>
            <Form.Item name="change_reason" label="记录依据" rules={[{ required: true, whitespace: true }]}><Input.TextArea maxLength={500} rows={3} /></Form.Item></>}
        <Button type="primary" htmlType="submit" loading={busy}>保存面试记录</Button>
      </Form>
    </Drawer>
  </>;
}
