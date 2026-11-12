import { useCallback, useState } from 'react';
import { Button, Card, Select, Space, Table, Tag } from 'antd';
import { Link } from 'react-router-dom';
import { api, type Task, type TaskFilters } from '../services/api';
import { useResource } from '../features/shared/useResource';
import { ErrorState } from '../components/RemoteState';
import PageHead from '../components/PageHead';
import FilterBar from '../features/recruitment/FilterBar';
import { filterParams, type Filters } from '../features/recruitment/filters';
import { formatTime } from '../features/recruitment/presentation';
import DeliveryQueue from '../features/wecom/DeliveryQueue';

const kinds = { interview: '即将面试', feedback: '待反馈', review: '待审核', stalled: '停滞申请', sync: '同步异常' };
export default function Tasks({ canWrite }: { canWrite: boolean }) {
  const [filters, setFilters] = useState<Filters>({});
  const [kind, setKind] = useState<TaskFilters['kind']>();
  const [page, setPage] = useState(1);
  const result = useResource(useCallback((signal: AbortSignal) => {
    const params = filterParams(filters);
    return api.tasks({ page, page_size: 8, kind, owner_id: params.owner_id, position_id: params.position_id, from: params.from, to: params.to }, signal);
  }, [filters, kind, page]));
  return <><PageHead title="面试与待办" desc="从实际面试、审核、停滞和同步记录生成。完成对应业务后自动移出；通知发送状态见下方记录，自动提醒由管理员配置。" />
    <Card><FilterBar stages={false} referenceDates onSearch={value => { setFilters(value); setPage(1); }} /></Card>
    {result.error && <ErrorState error={result.error} retry={result.reload} />}
    <Card className="section-card" title="待处理事项" extra={<Space wrap><Select aria-label="待办类别" allowClear placeholder="全部类别" style={{ minWidth: 130 }} value={kind}
      options={Object.entries(kinds).map(([value, label]) => ({ value, label }))} onChange={value => { setKind(value); setPage(1); }} /><Button onClick={result.reload}>刷新</Button></Space>}>
      <Table<Task> rowKey="id" loading={result.loading} dataSource={result.data?.data ?? []} scroll={{ x: 850 }} locale={{ emptyText: '当前范围没有待处理事项' }}
        pagination={{ current: page, pageSize: 8, total: result.data?.pagination.total ?? 0, onChange: setPage, showSizeChanger: false }} columns={[
          { title: '类别', dataIndex: 'kind', width: 120, render: (value: Task['kind']) => <Tag color={value === 'sync' ? 'red' : 'blue'}>{kinds[value]}</Tag> },
          { title: '事项', dataIndex: 'title', width: 150 }, { title: '申请', dataIndex: 'application_code', width: 170, render: (value, row) => row.application_id ? <Link to={`/applications/${row.application_id}?tab=${row.kind === 'interview' || row.kind === 'feedback' ? 'interviews' : 'basic'}`}>{value}</Link> : '尚待明确申请' },
          { title: '候选人 / 岗位', key: 'person', width: 180, render: (_, row) => `${row.candidate_name ?? '待识别'} · ${row.position_title ?? '待识别'}` },
          { title: '参考时间（上海）', dataIndex: 'at', width: 190, render: formatTime },
          { title: '操作', key: 'action', width: 90, render: (_, row) => row.kind === 'review' && canWrite ? <Link to="/ai-inbox">去审核</Link> : row.application_id ? <Link to={`/applications/${row.application_id}?tab=${['interview', 'feedback'].includes(row.kind) ? 'interviews' : 'history'}`}>查看记录</Link> : '请HR处理' },
        ]} />
      <p className="chart-note">参考时间：面试为计划时点，审核与同步为任务创建时间，停滞为最后更新时间（已超过7天）。</p>
    </Card><DeliveryQueue /></>;
}
