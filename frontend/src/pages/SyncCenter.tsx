import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { api, errorMessage, type SyncJob, type SyncState, type SyncSummary } from '../services/api';
import PageHead from '../components/PageHead';
import { formatTime } from '../features/recruitment/presentation';
import { SYNC_STATES, syncErrorLabel } from '../features/sync/presentation';

export default function SyncCenter() {
  const [jobs, setJobs] = useState<SyncJob[]>([]);
  const [summary, setSummary] = useState<SyncSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<SyncState>();
  const [total, setTotal] = useState(0);
  const [review, setReview] = useState<{ row: SyncJob; reason: string; key: string } | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState('');

  const load = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [result, counts] = await Promise.all([api.syncJobs(page, 8, status, signal), api.syncSummary(signal)]);
      if (signal?.aborted) return;
      setJobs(result.data); setTotal(result.pagination.total); setSummary(counts); setError('');
    } catch (cause) {
      if (!signal?.aborted) setError(errorMessage(cause, '同步任务读取失败，请检查后端连接并刷新'));
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [page, status]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal, true), 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);

  const run = async () => {
    setBusy(true);
    try { const result = await api.runMockSync(); message.info(result.message); await load(); }
    catch (cause) { setError(errorMessage(cause, '后台处理请求失败，请刷新后重试')); }
    finally { setBusy(false); }
  };

  const retry = async () => {
    if (!review?.reason.trim()) { setRetryError('请填写检查或恢复情况，作为重试审计说明'); return; }
    setRetrying(true);
    try {
      await api.retrySync(review.row, review.reason.trim(), review.key);
      setReview(null); setRetryError(''); message.info('已重新排队，实际同步结果将自动刷新'); await load();
    } catch (cause) { setRetryError(errorMessage(cause, '重试请求失败；如任务版本已变化，请关闭窗口并刷新')); }
    finally { setRetrying(false); }
  };

  return <>
    <PageHead title="同步中心" desc="本地业务已提交后，再由后台同步协作表。远端失败不会撤销招聘记录；每 5 秒刷新任务状态。" />
    <Alert type="warning" showIcon message={summary?.provider === 'tencent_docs' ? '腾讯文档写入受阻' : '当前使用本机 Mock 智能表格'}
      description={`${summary?.tencent_docs === 'blocked_by_schema' ? '已配置 Token，工具 Schema 与字段映射尚未验证。' : '腾讯文档尚未配置 Token。'} Mock 任务只写本机模拟表，MOCK- 标识不代表腾讯文档写入成功。`} />
    {error && <Alert className="section-card" type="error" showIcon message={error} action={<Button onClick={() => void load()}>重新加载</Button>} />}
    {summary && <Descriptions className="section-card" size="small" column={{ xs: 1, sm: 2, lg: 3 }} items={[
      { key: 'pending', label: '待同步 / 处理中', children: `${summary.counts.pending ?? 0} / ${summary.counts.processing ?? 0}` },
      { key: 'failed', label: '失败 / 死信', children: `${summary.counts.failed ?? 0} / ${summary.counts.dead ?? 0}` },
      { key: 'success', label: '最近投影成功', children: summary.last_success_at ? `${formatTime(summary.last_success_at)}（含模拟）` : '尚无成功记录' },
      { key: 'worker', label: '后台处理器', children: summary.worker_enabled ? '已启用 · 每 2 秒扫描' : '已关闭，需在服务端启用' },
    ]} />}
    <Card className="section-card" title="同步任务" extra={<Space wrap>
      <Button onClick={() => void load()} loading={loading}>刷新</Button>
      <Button type="primary" loading={busy} disabled={!summary?.worker_enabled} onClick={() => void run()}>请求后台处理</Button>
    </Space>}>
      <Select aria-label="同步任务状态" value={status} allowClear placeholder="全部任务状态" style={{ minWidth: 210 }}
        options={Object.entries(SYNC_STATES).map(([value, info]) => ({ value, label: info.label }))}
        onChange={(value: SyncState | undefined) => { setStatus(value); setPage(1); }} />
      <Table<SyncJob> rowKey="id" dataSource={jobs} loading={loading} scroll={{ x: 1550 }}
        locale={{ emptyText: error ? '暂时无法读取任务，请重新加载' : '当前条件下没有同步任务' }}
        pagination={{ current: page, pageSize: 8, total, showSizeChanger: false, onChange: setPage }} columns={[
          { title: '任务 / 申请', key: 'identity', width: 260, render: (_, row) => <Space direction="vertical" size={0}>
            <Typography.Text copyable={{ text: row.id }}>任务 {row.id.slice(0, 8)}</Typography.Text>
            <Typography.Text type="secondary" copyable={row.application_id ? { text: row.application_id } : false}>{row.application_id ? `申请 ${row.application_id.slice(0, 8)}` : row.entity_type}</Typography.Text>
          </Space> },
          { title: '目标', key: 'target', width: 150, render: (_, row) => row.internal_only ? '内部事件（不投影）' : row.provider === 'mock' ? 'Mock 智能表格' : '腾讯文档' },
          { title: '业务版本', dataIndex: 'version', width: 85 },
          { title: '状态', dataIndex: 'status', width: 190, render: (value: SyncState) => <Tag color={SYNC_STATES[value].color}>{SYNC_STATES[value].label}</Tag> },
          { title: '尝试（本轮 / 累计）', key: 'attempts', width: 140, render: (_, row) => `${row.cycle_attempts} / ${row.attempts}` },
          { title: '最近错误', dataIndex: 'last_error', width: 260, render: syncErrorLabel },
          { title: '下次重试（上海时间）', dataIndex: 'next_retry_at', width: 200, render: (value: string | null) => value ? formatTime(value) : '—' },
          { title: '远端记录 ID', dataIndex: 'remote_record_id', width: 220, ellipsis: true, render: (value: string | null) => value || '—' },
          { title: '操作', key: 'action', fixed: 'right', width: 110, render: (_, row) => ['failed', 'dead'].includes(row.status)
            ? <Button size="small" onClick={() => { setRetryError(''); setReview({ row, reason: '', key: crypto.randomUUID() }); }}>人工重试</Button> : '—' },
        ]} />
    </Card>
    <Modal title="重新排队同步任务" open={!!review} okText="确认重试" cancelText="取消" confirmLoading={retrying}
      onOk={() => void retry()} onCancel={() => { if (!retrying) setReview(null); }} maskClosable={!retrying} keyboard={!retrying}>
      <p>请先排查失败原因。重试将重新排队当前业务版本，并保留累计尝试次数和审计记录。</p>
      <p>{syncErrorLabel(review?.row.last_error ?? null)}</p>
      <label htmlFor="sync-retry-reason">重试说明（必填）</label>
      <Input.TextArea id="sync-retry-reason" value={review?.reason ?? ''} maxLength={300} showCount rows={3} disabled={retrying}
        onChange={event => setReview(value => value ? { ...value, reason: event.target.value, key: crypto.randomUUID() } : null)} />
      {retryError && <Alert className="section-card" type="error" showIcon message={retryError} />}
    </Modal>
  </>;
}
