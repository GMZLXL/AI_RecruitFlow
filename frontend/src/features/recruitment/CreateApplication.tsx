import { useCallback, useState } from 'react';
import { Alert, Button, Drawer, Form, Input, Radio, Select, message } from 'antd';
import { api, errorMessage, type ApplicationCreate } from '../../services/api';
import { useResource } from '../shared/useResource';

type Fields = ApplicationCreate & { mode: 'new' | 'existing' };
export default function CreateApplication({ done }: { done: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm<Fields>();
  const mode = Form.useWatch('mode', form);
  const options = useResource(useCallback((signal: AbortSignal) => api.options('', signal), []));
  const [candidates, setCandidates] = useState<{ value: string; label: string }[]>([]);
  const find = async (keyword = '') => {
    try { const result = await api.candidates(keyword); setCandidates(result.data.map(row => ({ value: row.id, label: `${row.display_name} · ${row.id.slice(0, 8)}` }))); }
    catch (cause) { setError(errorMessage(cause, '候选人读取失败，请重试搜索')); }
  };
  const save = async (values: Fields) => {
    setBusy(true); setError('');
    try {
      await api.addApplication({ candidate_name: values.mode === 'new' ? values.candidate_name : undefined,
        candidate_id: values.mode === 'existing' ? values.candidate_id : undefined, position_id: values.position_id,
        application_code: values.application_code?.trim() || undefined, source_channel: values.source_channel?.trim() || undefined }, key);
      setOpen(false); form.resetFields(); done(); message.success('申请已保存到本地，外部投影由后台处理');
    } catch (cause) { setError(errorMessage(cause, '新增失败，请核对字段后重试')); }
    finally { setBusy(false); }
  };
  return <><Button type="primary" onClick={() => { setOpen(true); setError(''); setKey(crypto.randomUUID()); }}>新增申请</Button>
    <Drawer title="新增候选人申请" width="min(540px, 100vw)" open={open} onClose={() => !busy && setOpen(false)}>
      {error && <Alert type="error" showIcon message={error} />}
      {options.error && <Alert type="error" message={options.error} action={<Button onClick={options.reload}>重新读取岗位</Button>} />}
      <Form form={form} layout="vertical" initialValues={{ mode: 'new' }} onFinish={value => void save(value)} onValuesChange={() => setKey(crypto.randomUUID())}>
        <Form.Item name="mode" label="候选人来源"><Radio.Group options={[{ value: 'new', label: '新增候选人' }, { value: 'existing', label: '已有候选人投递其他岗位' }]} /></Form.Item>
        {mode === 'existing' ? <Form.Item name="candidate_id" label="已有候选人（按姓名搜索后选择）" rules={[{ required: true }]}><Select showSearch filterOption={false} onFocus={() => void find()} onSearch={value => void find(value)} options={candidates} /></Form.Item>
          : <Form.Item name="candidate_name" label="候选人姓名" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} placeholder="仅录入已授权资料；演示使用虚构姓名" /></Form.Item>}
        <Form.Item name="position_id" label="岗位" rules={[{ required: true, message: '请选择已配置岗位' }]}><Select showSearch optionFilterProp="label" loading={options.loading} options={options.data?.positions.map(row => ({ value: row.id, label: `${row.title} · ${row.department}` }))} /></Form.Item>
        <p className="chart-note">没有可选岗位时，请管理员在系统设置中创建。不同申请保持独立阶段；同名不会自动合并。</p>
        <Form.Item name="application_code" label="申请编号（选填，留空自动生成）" rules={[{ pattern: /^[A-Z0-9_-]*$/, message: '仅大写字母、数字、下划线或短横线' }]}><Input maxLength={40} /></Form.Item>
        <Form.Item name="source_channel" label="来源渠道"><Input maxLength={100} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>保存申请</Button>
      </Form>
    </Drawer></>;
}
