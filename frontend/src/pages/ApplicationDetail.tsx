import { useCallback } from 'react';
import { Alert, Button, Card, Descriptions, Space, Tabs, Tag } from 'antd';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, type User } from '../services/api';
import { useResource } from '../features/shared/useResource';
import { ErrorState, LoadState } from '../components/RemoteState';
import PageHead from '../components/PageHead';
import { StageTag, SyncTag } from '../features/recruitment/StatusTags';
import StageEditor from '../features/recruitment/StageEditor';
import InterviewPanel from '../features/recruitment/InterviewPanel';
import OfferPanel from '../features/recruitment/OfferPanel';
import HistoryPanel from '../features/recruitment/HistoryPanel';
import { formatTime } from '../features/recruitment/presentation';

export default function ApplicationDetail({ identity }: { identity: User }) {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const result = useResource(useCallback((signal: AbortSignal) => api.application(id, signal), [id]));
  if (result.error) return <><Link to="/candidates">返回申请列表</Link><ErrorState error={result.error} retry={result.reload} /></>;
  if (result.loading || !result.data) return <LoadState />;
  const row = result.data;
  const canWrite = identity.role === 'ADMIN' || (identity.role === 'HR' && row.owner_id === identity.id);
  return <>
    <Link to="/candidates">返回申请列表</Link>
    <PageHead title={`${row.candidate_name} · ${row.position_title}`} desc={`申请 ${row.application_code} · 负责人 ${row.owner_name ?? '—'} · v${row.version}`} />
    <Space wrap className="detail-actions"><StageTag stage={row.stage} /><SyncTag status={row.sync_status} />{row.source_channel === '演示样本' && <Tag color="gold">虚构演示数据</Tag>}
      <Button onClick={result.reload}>刷新记录</Button>{canWrite && <StageEditor row={row} changed={result.reload} />}</Space>
    {!canWrite && <Alert type="info" message="当前身份仅可查看该申请，业务修改由负责人或管理员执行" />}
    <Card className="section-card"><Tabs activeKey={params.get('tab') ?? 'basic'} onChange={key => setParams({ tab: key })} destroyOnHidden items={[
      { key: 'basic', label: '基础信息', children: <Descriptions column={{ xs: 1, sm: 2 }} items={[
        { key: 'code', label: '申请编号', children: row.application_code }, { key: 'candidate', label: '候选人', children: row.candidate_name },
        { key: 'position', label: '岗位', children: row.position_title }, { key: 'owner', label: '负责人', children: row.owner_name },
        { key: 'source', label: '来源渠道', children: row.source_channel ?? '未记录' }, { key: 'created', label: '申请创建（上海）', children: formatTime(row.created_at) },
        { key: 'updated', label: '最近更新（上海）', children: formatTime(row.updated_at) }, { key: 'next', label: '下次面试（上海）', children: row.next_interview_at ? formatTime(row.next_interview_at) : '暂无未来计划' },
        { key: 'custom', label: '组织备注', children: row.custom_fields['organization.referral_tag'] ?? '—' },
      ]} /> },
      { key: 'interviews', label: '面试记录', children: <InterviewPanel application={row} canWrite={canWrite} changed={result.reload} /> },
      { key: 'offer', label: 'Offer记录', children: <OfferPanel application={row} canWrite={canWrite} changed={result.reload} /> },
      { key: 'history', label: '操作与审核历史', children: <><p>以下为授权范围内的业务与审核留痕，不包含原始消息或联系方式。当前投影：<SyncTag status={row.sync_status} /></p><HistoryPanel id={id} />{identity.role === 'ADMIN' && <Link to="/sync">查看同步任务详情</Link>}</> },
    ]} /></Card>
  </>;
}
