import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Form, Input, Table, Tag, message } from 'antd';
import { api, errorMessage, type Application, type ApplicationCreate, type Stage } from '../services/api';
import PageHead from '../components/PageHead';
import { STAGES, NEXT_STAGE, formatTime } from '../features/recruitment/presentation';
export default function Candidates({ canWrite }: { canWrite: boolean }) {
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
