import { useCallback, useState } from 'react';
import { Table } from 'antd';
import { api, type History } from '../../services/api';
import { useResource } from '../shared/useResource';
import { ErrorState } from '../../components/RemoteState';
import { formatTime, stageLabel } from './presentation';

const actions: Record<string, string> = { create_application: '创建申请', update_application: '更新申请', create_interview: '安排面试', update_interview: '反馈面试', interview_changed: '面试或Offer关联更新', record_offer_sent: '登记Offer发出', record_offer_response: '登记Offer反馈', seed_demo_history: '初始化虚构历史日期', resolve_confirmation: '处理人工审核' };
export default function HistoryPanel({ id }: { id: string }) {
  const [page, setPage] = useState(1);
  const history = useResource(useCallback((signal: AbortSignal) => api.history(id, page, signal), [id, page]));
  return <>{history.error && <ErrorState error={history.error} retry={history.reload} />}
    <Table<History> rowKey="id" dataSource={history.data?.data ?? []} loading={history.loading} scroll={{ x: 850 }}
      pagination={{ current: page, pageSize: 8, total: history.data?.pagination.total ?? 0, onChange: setPage, showSizeChanger: false }} columns={[
        { title: '时间（上海）', dataIndex: 'created_at', width: 190, render: formatTime },
        { title: '操作人', dataIndex: 'actor_name', width: 130 }, { title: '操作', dataIndex: 'action', width: 170, render: value => actions[value] ?? value },
        { title: '变更摘要', dataIndex: 'changes', render: (changes: History['changes']) => Object.entries(changes).map(([key, value]) => <div key={key}>{key === 'stage' ? '阶段' : key}：{key === 'stage' ? value.split(' → ').map(stageLabel).join(' → ') : value}</div>) },
        { title: '依据（已脱敏）', dataIndex: 'reason', width: 240 },
      ]} />
  </>;
}
