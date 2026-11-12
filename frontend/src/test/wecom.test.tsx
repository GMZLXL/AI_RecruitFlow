import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { api, type Notification } from '../services/api';
import WecomPanel from '../features/wecom/WecomPanel';
import DeliveryQueue from '../features/wecom/DeliveryQueue';
import { admin, list } from './fixtures';

vi.mock('../services/api', async importOriginal => {
  const original = await importOriginal<typeof import('../services/api')>();
  return { ...original, api: Object.fromEntries(Object.keys(original.api).map(key => [key, vi.fn()])) };
});
const show = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>);
const policy = { id: admin.id, version: 4, created_at: admin.created_at, updated_at: admin.updated_at,
  enabled: false, interview_hours: 24, feedback_hours: 24, stalled_days: 7, timezone: 'Asia/Shanghai' as const };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.wecomStatus).mockResolvedValue({ provider: 'mock', callback: 'mock_only', sending: 'mock_only', worker_enabled: true, callback_path: '/api/v1/webhooks/wecom', notice: '模拟' });
  vi.mocked(api.wecomUsers).mockResolvedValue(list([]));
  vi.mocked(api.wecomInbox).mockResolvedValue(list([]));
  vi.mocked(api.notifications).mockResolvedValue(list([]));
  vi.mocked(api.reminderPolicy).mockResolvedValue(policy);
});

it('模拟投稿失败保留消息ID，再试才显示已接收', async () => {
  const user = userEvent.setup();
  vi.mocked(api.mockWecom).mockRejectedValueOnce(new Error('synthetic failure')).mockResolvedValueOnce({
    id: admin.id, version: 1, created_at: admin.created_at, updated_at: admin.updated_at,
    provider: 'mock', status: 'pending', ingestion_id: null, last_error: null, attempts: 0,
  });
  show(<WecomPanel />);
  await user.click(await screen.findByRole('tab', { name: '模拟投稿' }));
  const eventInput = screen.getByLabelText('模拟消息ID') as HTMLInputElement;
  const originalId = eventInput.value;
  fireEvent.change(screen.getByLabelText('招聘消息'), { target: { value: 'A10001进入筛选' } });
  await user.click(screen.getByRole('button', { name: '提交模拟消息' }));
  await screen.findByText('投稿失败，请保留原消息ID重试');
  expect(eventInput.value).toBe(originalId);
  expect(screen.queryByText('已接收，等待后台处理。')).toBeNull();
  await user.click(screen.getByRole('button', { name: '提交模拟消息' }));
  await screen.findByRole('link', { name: '查看AI录入与审核' });
  expect(api.mockWecom).toHaveBeenNthCalledWith(2, { message_id: originalId, text: 'A10001进入筛选' }, expect.any(String));
  expect(vi.mocked(api.mockWecom).mock.calls[0][1]).toBe(vi.mocked(api.mockWecom).mock.calls[1][1]);
}, 10000);

it('提醒规则409保留输入，携带服务端版本且只提交契约字段', async () => {
  const user = userEvent.setup();
  vi.mocked(api.updateReminderPolicy).mockRejectedValue(new Error('synthetic conflict'));
  show(<WecomPanel />);
  await user.click(await screen.findByRole('tab', { name: '提醒规则' }));
  await screen.findByLabelText('申请未更新（天）');
  fireEvent.change(screen.getByLabelText('申请未更新（天）'), { target: { value: '9' } });
  fireEvent.change(screen.getByLabelText('提醒变更依据'), { target: { value: '虚构测试调整' } });
  await user.click(screen.getByRole('button', { name: '保存提醒规则' }));
  await screen.findByText('规则保存失败；版本冲突时刷新后重新核对');
  expect(screen.getByLabelText('申请未更新（天）')).toHaveValue('9');
  expect(api.updateReminderPolicy).toHaveBeenCalledWith(policy, { enabled: false, interview_hours: 24, feedback_hours: 24, stalled_days: 9, change_reason: '虚构测试调整' }, expect.any(String));
  vi.mocked(api.reminderPolicy).mockResolvedValue({ ...policy, version: 5, stalled_days: 12 });
  await user.click(screen.getByRole('button', { name: '刷新规则版本，保留草稿' }));
  await screen.findByText(/停滞12天（版本5）/);
  expect(screen.getByLabelText('申请未更新（天）')).toHaveValue('9');
  expect(screen.getByLabelText('提醒变更依据')).toHaveValue('虚构测试调整');
  await user.click(screen.getByRole('button', { name: '刷新企微状态' }));
  await waitFor(() => expect(screen.getByRole('tab', { name: '提醒规则' })).toHaveAttribute('aria-selected', 'true'));
  expect(screen.getByLabelText('申请未更新（天）')).toHaveValue('9');
  vi.mocked(api.updateReminderPolicy).mockResolvedValue({ ...policy, version: 6, stalled_days: 9 });
  await user.click(screen.getByRole('button', { name: '保存提醒规则' }));
  await screen.findByText('提醒规则已保存，当前为关闭（版本6）');
  expect(api.updateReminderPolicy).toHaveBeenLastCalledWith({ ...policy, version: 5, stalled_days: 12 }, { enabled: false, interview_hours: 24, feedback_hours: 24, stalled_days: 9, change_reason: '虚构测试调整' }, expect.any(String));
}, 10000);

it('用户绑定成功有确认，刷新版本保留外部ID和说明草稿', async () => {
  const user = userEvent.setup();
  const binding = { id: admin.id, version: 1, created_at: admin.created_at, updated_at: admin.updated_at, display_name: '虚构内部用户', role: 'HR', external_wecom_userid: null };
  vi.mocked(api.wecomUsers).mockResolvedValue(list([binding]));
  vi.mocked(api.bindWecomUser).mockResolvedValue({ ...binding, version: 2, external_wecom_userid: 'synthetic-hr' });
  show(<WecomPanel />);
  await user.click(await screen.findByLabelText('内部用户（当前页）'));
  await user.click(await screen.findByText('虚构内部用户', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(screen.getByRole('tabpanel', { name: '接入与用户绑定' })).toHaveTextContent('最新已保存：虚构内部用户'));
  fireEvent.change(screen.getByLabelText('企微成员UserID（留空解除绑定）'), { target: { value: 'synthetic-hr' } });
  fireEvent.change(screen.getByLabelText('绑定变更依据'), { target: { value: '虚构绑定依据' } });
  await user.click(screen.getByRole('button', { name: '刷新用户版本，保留草稿' }));
  expect(screen.getByLabelText('企微成员UserID（留空解除绑定）')).toHaveValue('synthetic-hr');
  expect(screen.getByLabelText('绑定变更依据')).toHaveValue('虚构绑定依据');
  await waitFor(() => expect(screen.getByRole('button', { name: '保存用户绑定' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: '保存用户绑定' }));
  await screen.findByText('虚构内部用户的企微绑定已保存（版本2）');
}, 10000);

it('结果不明不提供重发；明确失败可填写理由后重试', async () => {
  const user = userEvent.setup();
  const base: Notification = { id: admin.id, version: 5, created_at: admin.created_at, updated_at: admin.updated_at,
    status: 'uncertain', provider: 'wecom', recipient_name: '虚构HR', application_id: null, text: '虚构通知', attempts: 1, last_error: 'SEND_RESULT_UNKNOWN', platform_message_id: null, completed_at: null };
  vi.mocked(api.notifications).mockResolvedValue(list([base]));
  const view = show(<DeliveryQueue admin />);
  await screen.findByText('结果不明，需核实');
  expect(screen.queryByRole('button', { name: '重试通知' })).toBeNull();
  vi.mocked(api.notifications).mockResolvedValue(list([{ ...base, status: 'failed' }]));
  await user.click(screen.getByRole('button', { name: '刷新通知' }));
  await user.click(await screen.findByRole('button', { name: '重试通知' }));
  fireEvent.change(screen.getByLabelText('重试依据'), { target: { value: '虚构配置已修正' } });
  vi.mocked(api.retryNotification).mockResolvedValue({ ...base, status: 'pending' });
  await user.click(screen.getByRole('button', { name: '确认重试' }));
  await waitFor(() => expect(api.retryNotification).toHaveBeenCalledWith({ ...base, status: 'failed' }, '虚构配置已修正', expect.any(String)));
  view.unmount();
});
