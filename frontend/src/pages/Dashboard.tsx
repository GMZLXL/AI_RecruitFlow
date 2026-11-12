import { lazy, Suspense, useCallback, useState } from 'react';
import { Button, Card, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import PageHead from '../components/PageHead';
import FilterBar from '../features/recruitment/FilterBar';
import { filterParams, recentDates, type Filters } from '../features/recruitment/filters';
import { useResource } from '../features/shared/useResource';
import { ErrorState, LoadState } from '../components/RemoteState';
const Charts = lazy(() => import('../features/dashboard/Charts'));
const initial = recentDates();

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>(initial);
  const result = useResource(useCallback((signal: AbortSignal) => api.dashboard(filterParams(filters), signal), [filters]));
  const data = result.data;
  return <>
    <PageHead title="招聘工作台" desc="按申请创建时间与授权范围查询。演示样本为虚构资料，指标由实际数据库记录计算。" />
    <Card className="filters-card"><FilterBar initial={initial} onSearch={setFilters} /></Card>
    {result.error ? <ErrorState error={result.error} retry={result.reload} /> : result.loading || !data ? <LoadState /> : <>
      <div className="metric-strip" aria-label="招聘指标">{[
        ['新增申请', data.new_applications], ['候选人数', data.candidates], ['待面试', data.upcoming_interviews], ['待反馈', data.pending_feedback],
        ['Offer已发出', data.offers_sent], ['已接受', data.offers_accepted], ['已拒绝', data.offers_declined], ['已录用', data.hired_applications],
      ].map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="dashboard-context"><Typography.Text>Offer接受率：<strong>{data.offer_acceptance_rate === null ? '暂无明确反馈' : `${(data.offer_acceptance_rate * 100).toFixed(1)}%`}</strong>（接受 ÷ 接受与拒绝，排除未反馈；接受不等于录用）</Typography.Text>
        <Link to="/tasks">查看面试与待办</Link><Button size="small" onClick={result.reload}>刷新数据</Button></div>
      <Typography.Paragraph type="secondary">{data.population}。未完成申请投影任务：{data.pending_sync}，不含内部事件。</Typography.Paragraph>
      <Suspense fallback={<LoadState />}><Charts data={data} /></Suspense>
    </>}
  </>;
}
