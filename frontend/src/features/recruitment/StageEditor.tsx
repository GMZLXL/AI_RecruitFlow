import { useState } from 'react';
import { Alert, Button, Drawer, Form, Input, Select, Typography, message } from 'antd';
import { Link } from 'react-router-dom';
import { api, errorMessage, type Application, type ApplicationPatch, type Stage } from '../../services/api';
import { NEXT_STAGE, STAGES } from './presentation';

export default function StageEditor({ row, changed }: { row: Application; changed: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm<ApplicationPatch>();
  const terminal = ['hired', 'rejected', 'withdrawn'].includes(row.stage);
  const forward: Stage | undefined = row.stage === 'offer' ? 'hired' : NEXT_STAGE[row.stage];
  const targets = terminal ? Object.keys(STAGES).filter(stage => stage !== row.stage) as Stage[] : [forward, 'rejected', 'withdrawn'].filter((stage): stage is Stage => !!stage);
  const submit = async (values: ApplicationPatch) => {
    setBusy(true); setError('');
    try {
      const result = await api.updateApplication(row, values, key);
      setOpen(false); changed();
      message.info(result.status === 'needs_confirmation' ? '终态逆转已进入AI审核队列，原状态保持不变' : '阶段已更新并留痕');
    } catch (cause) { setError(errorMessage(cause, '更新失败，请关闭窗口刷新版本后重试')); }
    finally { setBusy(false); }
  };
  return <><Button type="primary" onClick={() => { setOpen(true); setError(''); setKey(crypto.randomUUID()); }}>更新阶段</Button>
    <Drawer title="人工更新招聘阶段" width="min(500px, 100vw)" open={open} onClose={() => !busy && setOpen(false)}>
      <Typography.Paragraph>当前：{STAGES[row.stage]} · 申请版本 {row.version}</Typography.Paragraph>
      {terminal && <Alert type="warning" message="终态逆转将创建审核任务，不直接修改原记录" />}
      {error && <Alert type="error" showIcon message={error} description="输入已保留；如版本已变化，请关闭并刷新记录后重新核对。" />}
      <Form form={form} layout="vertical" onFinish={values => void submit(values)} onValuesChange={() => setKey(crypto.randomUUID())}>
        <Form.Item name="stage" label="目标阶段" rules={[{ required: true }]}><Select options={targets.map(value => ({ value, label: STAGES[value] }))} /></Form.Item>
        <Form.Item name="change_reason" label="变更依据" rules={[{ required: true, whitespace: true, message: '请填写人工核实依据' }]}><Input.TextArea rows={3} maxLength={500} /></Form.Item>
        <p>录用或淘汰由授权人员核实记录，AI不会自动做出决定。</p>
        <Button type="primary" htmlType="submit" loading={busy}>提交变更</Button> <Link to="/ai-inbox">查看审核队列</Link>
      </Form>
    </Drawer></>;
}
