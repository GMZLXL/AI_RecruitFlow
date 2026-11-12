import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError } from 'axios';
import { api } from '../services/api';
import Dashboard from '../pages/Dashboard';
import Candidates from '../pages/Candidates';
import StageEditor from '../features/recruitment/StageEditor';
import OfferPanel from '../features/recruitment/OfferPanel';
import AIInbox from '../pages/AIInbox';
import App from '../app/App';
import ReviewQueue from '../features/ai/ReviewQueue';
import { application, admin, emptyDashboard, list } from './fixtures';

vi.mock('../services/api', async importOriginal => {
  const original = await importOriginal<typeof import('../services/api')>();
  return { ...original, api: Object.fromEntries(Object.keys(original.api).map(key => [key, vi.fn()])) };
});
vi.mock('../features/dashboard/Charts', () => ({ default: () => <div data-testid="charts">数据库图表</div> }));

const failure = (status: number, message: string) => Object.assign(new AxiosError('synthetic-error'), { response: { status, data: { error: { code: 'SYNTHETIC', message } } } });
const show = (node: React.ReactNode, route = '/') => render(<MemoryRouter initialEntries={[route]}>{node}</MemoryRouter>);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.authConfig).mockResolvedValue({ authentication: 'development_only', mode: 'mock', login_url: null, logout_url: null });
  vi.mocked(api.options).mockResolvedValue({ positions: [], owners: [], limit: 100 });
  vi.mocked(api.confirmations).mockResolvedValue(list([]));
});

describe('看板与列表', () => {
  it('API失败可重试，空数据接受率不伪造为0%', async () => {
    vi.mocked(api.dashboard).mockRejectedValueOnce(failure(500, '读取暂时失败')).mockResolvedValue(emptyDashboard);
    show(<Dashboard />);
    await screen.findByText('读取暂时失败');
    await userEvent.click(screen.getByRole('button', { name: '重新加载' }));
    await screen.findByText('暂无明确反馈');
    expect(screen.getByLabelText('招聘指标')).toHaveTextContent('新增申请0');
  });

  it('日期查询传递上海起止区间，不改变输入', async () => {
    vi.mocked(api.dashboard).mockResolvedValue(emptyDashboard);
    show(<Dashboard />);
    await screen.findByText('暂无明确反馈');
    fireEvent.change(screen.getByLabelText('申请创建起日（上海）'), { target: { value: '2026-02-28' } });
    fireEvent.change(screen.getByLabelText('申请创建止日（含当天）'), { target: { value: '2026-03-01' } });
    await userEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
    await waitFor(() => expect(api.dashboard).toHaveBeenLastCalledWith(expect.objectContaining({ from: '2026-02-28T00:00:00+08:00', to: '2026-03-02T00:00:00+08:00' }), expect.any(AbortSignal)));
  });

  it('候选人搜索由API执行，详情链接可用，只读身份无新增按钮', async () => {
    vi.mocked(api.applications).mockResolvedValue(list([application]));
    show(<Candidates canWrite={false} />);
    await screen.findByRole('link', { name: application.application_code });
    expect(screen.getByRole('link', { name: application.application_code })).toHaveAttribute('href', `/applications/${application.id}`);
    expect(screen.queryByRole('button', { name: '新增申请' })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('姓名或申请编号'), '林沐');
    await userEvent.type(screen.getByLabelText('来源渠道'), '演示样本');
    await userEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
    await waitFor(() => expect(api.applications).toHaveBeenLastCalledWith(1, 8, '林沐', expect.objectContaining({ keyword: '林沐', source_channel: '演示样本' }), expect.any(AbortSignal)));
  });
});

describe('受控写入', () => {
  it('Web审核显式选择申请并携带版本和人工说明', async () => {
    const row = { id: 'confirmation-synthetic', application_id: application.id, reason: 'NAME_ONLY_MATCH', status: 'pending' as const,
      version: 1, created_at: application.created_at, updated_at: application.updated_at, message_excerpt: '虚构姓名更新',
      target_stage: 'screening' as const, candidates: [application], expected_application_version: application.version };
    vi.mocked(api.confirmations).mockResolvedValue(list([row]));
    vi.mocked(api.resolve).mockResolvedValue({ confirmation_id: row.id, status: 'confirmed', version: 2, application: { ...application, stage: 'screening' } });
    const onResolved = vi.fn();
    show(<ReviewQueue refreshKey={0} onResolved={onResolved} />);
    await userEvent.click(await screen.findByRole('button', { name: /审\s*核/ }));
    expect(screen.queryByLabelText('候选人姓名（新增时）')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('面试轮次')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('审核说明'), '已核对虚构申请编号');
    await userEvent.click(screen.getByRole('button', { name: '确认原提议' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ status: 'confirmed' })));
    expect(api.resolve).toHaveBeenCalledWith(expect.objectContaining({ id: row.id }), expect.objectContaining({ application_id: application.id, expected_application_version: 1, change_reason: '已核对虚构申请编号' }));
  });
  it('阶段冲突保留人工依据，不自动重放覆盖', async () => {
    vi.mocked(api.updateApplication).mockRejectedValue(failure(409, '版本已更新，请刷新'));
    show(<StageEditor row={application} changed={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: '更新阶段' }));
    await userEvent.click(screen.getByLabelText('目标阶段'));
    await userEvent.click(await screen.findByText('简历筛选'));
    await userEvent.type(screen.getByLabelText('变更依据'), '人工核对虚构样本');
    await userEvent.click(screen.getByRole('button', { name: '提交变更' }));
    await screen.findByText('版本已更新，请刷新');
    expect(screen.getByLabelText('变更依据')).toHaveValue('人工核对虚构样本');
    expect(api.updateApplication).toHaveBeenCalledTimes(1);
  });

  it('Offer接受仅登记反馈，不自动录用', async () => {
    const now = new Date().toISOString();
    vi.mocked(api.offer).mockResolvedValue({ id: 'offer-synthetic', application_id: application.id, status: 'sent', sent_at: '2026-01-01T00:00:00Z', responded_at: null, version: 1, created_at: now, updated_at: now });
    const changed = vi.fn();
    show(<OfferPanel application={{ ...application, stage: 'offer' }} canWrite changed={changed} />);
    await screen.findByText('已发出 · 待反馈');
    await userEvent.click(screen.getByLabelText('候选人明确反馈'));
    await userEvent.click(await screen.findByText('接受Offer'));
    await userEvent.type(screen.getByLabelText('登记依据'), '已核对虚构明确反馈');
    await userEvent.click(screen.getByRole('button', { name: '登记反馈' }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(api.respondOffer).toHaveBeenCalledWith(application.id, expect.objectContaining({ version: 1 }), expect.objectContaining({ status: 'accepted' }), expect.any(String));
    expect(api.updateApplication).not.toHaveBeenCalled();
  });

  it('AI请求失败重试复用事件ID，保留消息', async () => {
    vi.mocked(api.ingest).mockRejectedValueOnce(failure(500, '暂时失败')).mockResolvedValue({ status: 'needs_confirmation', reason: '请补全目标', parser_provider: 'mock', mode: 'mock' });
    show(<AIInbox />);
    await userEvent.type(screen.getByLabelText('招聘业务消息'), '虚构林沐一面通过');
    await userEvent.click(screen.getByRole('button', { name: /解析并处理/ }));
    await screen.findByText('暂时失败');
    await userEvent.click(screen.getByRole('button', { name: /解析并处理/ }));
    await screen.findByText('请补全目标');
    expect(vi.mocked(api.ingest).mock.calls[0][1]).toBe(vi.mocked(api.ingest).mock.calls[1][1]);
    expect(screen.getByLabelText('招聘业务消息')).toHaveValue('虚构林沐一面通过');
  });
});

describe('路由权限', () => {
  it('负责人直接访问同步路由仍被阻断，且不调用管理员API', async () => {
    vi.mocked(api.me).mockResolvedValue({ user: { ...admin, role: 'MANAGER' }, mode: 'mock', authentication: 'development_only' });
    vi.mocked(api.devUsers).mockResolvedValue([]);
    show(<App />, '/sync');
    await screen.findByText('仅管理员可以访问同步中心');
    expect(api.syncJobs).not.toHaveBeenCalled();
    expect(screen.queryByRole('menuitem', { name: '同步中心' })).not.toBeInTheDocument();
  });

  it('认证失败显示恢复路径，不渲染私有业务页面', async () => {
    vi.mocked(api.me).mockRejectedValue(failure(401, '开发身份未启用'));
    vi.mocked(api.devUsers).mockResolvedValue([]);
    show(<App />, '/candidates');
    await screen.findByText('开发身份未启用');
    expect(screen.getByRole('button', { name: '恢复默认开发身份' })).toBeInTheDocument();
    expect(api.applications).not.toHaveBeenCalled();
  });
});
