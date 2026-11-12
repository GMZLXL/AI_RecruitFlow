import { useCallback, useState } from 'react';
import { Button, Card, Space, Table, Tag } from 'antd';
import { Link } from 'react-router-dom';
import { api, type Application } from '../services/api';
import PageHead from '../components/PageHead';
import FilterBar from '../features/recruitment/FilterBar';
import CreateApplication from '../features/recruitment/CreateApplication';
import { filterParams, type Filters } from '../features/recruitment/filters';
import { formatTime } from '../features/recruitment/presentation';
import { StageTag, SyncTag } from '../features/recruitment/StatusTags';
import { useResource } from '../features/shared/useResource';
import { ErrorState } from '../components/RemoteState';

export default function Candidates({ canWrite }: { canWrite: boolean }) {
  const [filters, setFilters] = useState<Filters>({});
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(8);
  const result = useResource(useCallback((signal: AbortSignal) => api.applications(page, pageSize, filters.keyword ?? '', filterParams(filters), signal), [page, pageSize, filters]));
  return <>
    <PageHead title="候选人与申请" desc="同一候选人可投递多个岗位，每条申请分别跟踪。列表只显示后端授权范围内的记录。" />
    <Card><FilterBar search onSearch={value => { setFilters(value); setPage(1); }} /></Card>
    {result.error && <ErrorState error={result.error} retry={result.reload} />}
    <Card className="section-card" title={`招聘申请${result.data ? ` · ${result.data.pagination.total}条` : ''}`} extra={<Space wrap><Button onClick={result.reload}>刷新</Button>{canWrite && <CreateApplication done={() => { setPage(1); result.reload(); }} />}</Space>}>
      <Table<Application> rowKey="id" loading={result.loading} dataSource={result.data?.data ?? []} scroll={{ x: 1370 }} locale={{ emptyText: result.error ? '数据读取失败，请重试' : '当前筛选下暂无申请，可调整条件或新增申请' }}
        pagination={{ current: page, pageSize, total: result.data?.pagination.total ?? 0, showSizeChanger: true, pageSizeOptions: [8, 20, 50], onChange: (next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); } }} columns={[
          { title: '申请编号', dataIndex: 'application_code', width: 170, render: (_, row) => <Link to={`/applications/${row.id}`}>{row.application_code}</Link> },
          { title: '候选人', dataIndex: 'candidate_name', width: 120, render: (name, row) => <>{name}{row.source_channel === '演示样本' && <Tag>虚构</Tag>}</> },
          { title: '岗位', dataIndex: 'position_title', width: 160 }, { title: '负责人', dataIndex: 'owner_name', width: 130 },
          { title: '阶段', dataIndex: 'stage', width: 120, render: value => <StageTag stage={value} /> },
          { title: '最近结果', dataIndex: 'latest_result', width: 100, render: value => value === 'passed' ? '通过' : value === 'failed' ? '未通过' : '—' },
          { title: '下次面试（上海）', dataIndex: 'next_interview_at', width: 190, render: value => value ? formatTime(value) : '—' },
          { title: '投影状态', dataIndex: 'sync_status', width: 160, render: value => <SyncTag status={value} /> },
          { title: '更新时间（上海）', dataIndex: 'updated_at', width: 190, render: formatTime },
          { title: '操作', key: 'action', fixed: 'right', width: 80, render: (_, row) => <Link to={`/applications/${row.id}`}>详情</Link> },
        ]} />
    </Card>
  </>;
}
