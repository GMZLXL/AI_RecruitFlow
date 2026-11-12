import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, Drawer, Form, Input, InputNumber, Select, Space, Table, Tag, message } from 'antd';
import { api, errorMessage, type Application, type Confirmation, type Extraction, type ResolveRequest, type Resolution } from '../../services/api';
import { STAGES } from '../recruitment/presentation';

type Fields = Partial<Extraction> & {
  application_id?: string; candidate_id?: string; position_id?: string; interview_id?: string;
  local_time?: string; change_reason: string; create_new_candidate?: boolean;
};

const blank: Extraction = { intent: 'unknown', should_confirm: true, source_spans: {}, missing_fields: [], ambiguities: [] };
const localTime = (value?: string | null) => value ? new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).slice(0, 16).replace(' ', 'T') : undefined;

export default function ReviewQueue({ refreshKey, onResolved }: { refreshKey: number; onResolved: (value: Resolution) => void }) {
  const [rows, setRows] = useState<Confirmation[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Confirmation | null>(null);
  const [choices, setChoices] = useState<Application[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form] = Form.useForm<Fields>();
  const intent = Form.useWatch('intent', form);
  const load = useCallback(async () => {
    setLoading(true);
    try { const result = await api.confirmations(page); setRows(result.data); setTotal(result.pagination.total); }
    catch (e) { message.error(errorMessage(e, '无法读取审核队列')); }
    finally { setLoading(false); }
  }, [page]);
  useEffect(() => { void load(); }, [load, refreshKey]);
  const open = (row: Confirmation) => {
    setSelected(row); setChoices(row.candidates ?? []); setError(''); form.resetFields();
    const proposal = row.proposal ?? { ...blank, intent: 'update_stage' as const, stage: row.target_stage };
    form.setFieldsValue({ ...proposal, application_id: row.application_id ?? undefined,
      local_time: localTime(proposal.next_interview?.scheduled_at ?? proposal.scheduled_at),
      interviewer: proposal.next_interview?.interviewer ?? proposal.interviewer,
      create_new_candidate: false, change_reason: '' });
  };
  const search = async (keyword: string) => {
    try {
      const found = await api.applications(1, 20, keyword);
      setChoices([...(selected?.candidates ?? []), ...found.data.filter(row => !selected?.candidates?.some(old => old.id === row.id))]);
    } catch (e) { message.error(errorMessage(e, '申请搜索失败')); }
  };
  const execute = async (decision: ResolveRequest['decision']) => {
    if (!selected) return;
    let values: Fields;
    try { values = await form.validateFields(decision === 'reject' ? ['change_reason'] : undefined); }
    catch { return; }
    const target = choices.find(row => row.id === values.application_id);
    const body: ResolveRequest = { decision, change_reason: values.change_reason, create_new_candidate: !!values.create_new_candidate,
      application_id: values.application_id, candidate_id: values.candidate_id || undefined, position_id: values.position_id || undefined,
      interview_id: values.interview_id || undefined,
      expected_application_version: target?.version ?? selected.expected_application_version ?? undefined };
    if (decision === 'modify') {
      const base = selected.proposal ?? blank;
      const scheduled = values.local_time ? `${values.local_time}:00+08:00` : undefined;
      body.correction = { ...base, intent: values.intent ?? base.intent, candidate_name: values.candidate_name,
        position_name: values.position_name, application_code: values.application_code || undefined, stage: values.stage,
        interview_round: values.interview_round, interview_result: values.interview_result,
        scheduled_at: base.next_interview ? base.scheduled_at : scheduled, interviewer: base.next_interview ? base.interviewer : values.interviewer,
        next_interview: base.next_interview ? { ...base.next_interview, scheduled_at: scheduled, interviewer: values.interviewer } : undefined,
        should_confirm: false, ambiguities: [], missing_fields: [] };
    }
    setBusy(true); setError('');
    try { const result = await api.resolve(selected, body); onResolved(result); setSelected(null); message.success(decision === 'reject' ? '已驳回并留痕' : '已审核执行并写入审计'); await load(); }
    catch (e) { setError(errorMessage(e, '审核失败，请刷新核对版本')); }
    finally { setBusy(false); }
  };
  return <Card className="section-card" title="待人工确认" extra={<Button onClick={() => void load()}>刷新</Button>}>
    <Table rowKey="id" dataSource={rows} loading={loading} scroll={{ x: 650 }} pagination={{ current: page, pageSize: 8, total, showSizeChanger: false, onChange: setPage }} columns={[
      { title: '原因', dataIndex: 'reason', render: value => <Tag color="orange">{value}</Tag> },
      { title: '消息摘要（已脱敏）', dataIndex: 'message_excerpt' },
      { title: '版本', dataIndex: 'version', width: 70 },
      { title: '操作', key: 'action', render: (_: unknown, row: Confirmation) => <Button onClick={() => open(row)}>审核</Button> },
    ]} />
    <Drawer title="人工确认招聘变更" width="min(540px, 100vw)" open={!!selected} onClose={() => !busy && setSelected(null)} destroyOnHidden>
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      <Form form={form} layout="vertical">
        <Form.Item name="application_id" label="目标申请（搜索编号或姓名，显式选择）"><Select allowClear showSearch filterOption={false} onSearch={value => void search(value)} onFocus={() => { if (!choices.length) void search(''); }} options={choices.map(row => ({ value: row.id, label: `${row.application_code} · ${row.candidate_name} · ${row.position_title} · v${row.version}` }))} /></Form.Item>
        <Form.Item name="intent" label="操作意图"><Select options={[
          { value: 'create_application', label: '新增申请' }, { value: 'record_result', label: '记录面试结果' },
          { value: 'schedule_interview', label: '安排面试' }, { value: 'update_stage', label: '更新阶段' }, { value: 'unknown', label: '未识别（请修正或驳回）' },
        ]} /></Form.Item>
        {intent === 'create_application' && <><Form.Item name="candidate_name" label="候选人姓名（新增时）"><Input maxLength={100} /></Form.Item>
          <Form.Item name="position_name" label="岗位名称（新增时）"><Input maxLength={120} /></Form.Item>
          <Form.Item name="application_code" label="申请编号（选填）"><Input maxLength={40} /></Form.Item>
          <Form.Item name="create_new_candidate" valuePropName="checked"><Checkbox>已核实为不同的人，确认新建同名候选人</Checkbox></Form.Item></>}
        {intent === 'update_stage' && <Form.Item name="stage" label="目标阶段"><Select allowClear options={Object.entries(STAGES).map(([value,label])=>({value,label}))} /></Form.Item>}
        {['record_result', 'schedule_interview'].includes(intent ?? '') && <Form.Item name="interview_round" label="面试轮次"><InputNumber min={1} max={30} /></Form.Item>}
        {intent === 'record_result' && <Form.Item name="interview_result" label="本轮结果"><Select allowClear options={[{value:'passed',label:'通过'},{value:'failed',label:'未通过'}]} /></Form.Item>}
        {(intent === 'schedule_interview' || selected?.proposal?.next_interview) && <>
          <Form.Item name="local_time" label={selected?.proposal?.next_interview ? '下一轮面试时间（上海）' : '面试时间（上海）'}><Input type="datetime-local" /></Form.Item>
          <Form.Item name="interviewer" label="面试官"><Input maxLength={100} /></Form.Item></>}
        <Collapse className="review-advanced" size="small" items={[{ key: 'matching', label: '高级匹配（复用资料或同轮多次面试）', children: <>
          <Form.Item name="candidate_id" label="使用已有候选人ID（新增申请时选填）"><Input maxLength={36} /></Form.Item>
          <Form.Item name="position_id" label="使用已有岗位ID（选填）"><Input maxLength={36} /></Form.Item>
          <Form.Item name="interview_id" label="明确面试ID（同轮多次面试时）"><Input maxLength={36} /></Form.Item>
        </> }]} />
        <Form.Item name="change_reason" label="审核说明" rules={[{required:true,whitespace:true,message:'请填写审核依据'}]}><Input.TextArea maxLength={500} rows={2} /></Form.Item>
        <Space wrap><Button type="primary" loading={busy} onClick={()=>void execute('confirm')}>确认原提议</Button><Button loading={busy} onClick={()=>void execute('modify')}>修正并执行</Button><Button danger disabled={busy} onClick={()=>void execute('reject')}>驳回</Button></Space>
      </Form>
    </Drawer>
  </Card>;
}
