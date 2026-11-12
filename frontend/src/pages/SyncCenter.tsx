import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Space, Table, Tag, message } from 'antd';
import { api, type SyncJob } from '../services/api';
import PageHead from '../components/PageHead';

export default function SyncCenter() {
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
