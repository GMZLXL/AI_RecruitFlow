import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { api, type AISettings } from '../services/api';
import AISettingsPanel from '../features/settings/AISettingsPanel';
import App from '../app/App';
import { admin } from './fixtures';

vi.mock('../services/api', async importOriginal => {
  const original = await importOriginal<typeof import('../services/api')>();
  return { ...original, api: Object.fromEntries(Object.keys(original.api).map(key => [key, vi.fn()])) };
});
const settings: AISettings = { provider: 'mock', model: 'synthetic-model', version: 1, has_api_key: true,
  key_source: 'managed', secret_store_ready: true, real_calls_allowed: false, status: 'mock_only' };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.aiSettings).mockResolvedValue(settings); });

it('Key只用于提交，成功后清空输入，不回填已保存Key或写浏览器存储', async () => {
  const saved = vi.fn();
  const local = vi.spyOn(Storage.prototype, 'setItem');
  vi.mocked(api.updateAISettings).mockResolvedValue({ ...settings, version: 2 });
  render(<AISettingsPanel onSaved={saved} />);
  const field = await screen.findByLabelText('DeepSeek API Key（留空保留当前Key）');
  expect(field).toHaveAttribute('type', 'password');
  expect(field).toHaveValue('');
  fireEvent.change(field, { target: { value: 'synthetic-private-ai-key' } });
  fireEvent.click(screen.getByRole('button', { name: '保存AI配置' }));
  await screen.findByText('AI配置已保存（版本2），Key已配置；当前使用Mock');
  expect(field).toHaveValue('');
  expect(saved).toHaveBeenCalledOnce();
  expect(local).not.toHaveBeenCalled();
  expect(api.updateAISettings).toHaveBeenCalledWith(settings,
    { provider: 'mock', model: 'synthetic-model', api_key: 'synthetic-private-ai-key', clear_api_key: false, change_reason: '管理员更新AI接入配置' }, expect.any(String));
  local.mockRestore();
});

it('409后刷新只更新版本基准，保留模型和Key草稿', async () => {
  vi.mocked(api.updateAISettings).mockRejectedValue(new Error('synthetic conflict'));
  render(<AISettingsPanel onSaved={() => undefined} />);
  const model = await screen.findByLabelText('模型名称');
  fireEvent.change(model, { target: { value: 'synthetic-draft-model' } });
  fireEvent.change(screen.getByLabelText('DeepSeek API Key（留空保留当前Key）'), { target: { value: 'synthetic-draft-key' } });
  fireEvent.click(screen.getByRole('button', { name: '保存AI配置' }));
  await screen.findByText('保存失败，请保留草稿重试；版本冲突时先刷新配置并核对');
  vi.mocked(api.aiSettings).mockResolvedValue({ ...settings, version: 4, model: 'synthetic-server-model' });
  fireEvent.click(screen.getByRole('button', { name: '刷新AI配置，保留草稿' }));
  await screen.findByText(/synthetic-server-model（版本4）/);
  expect(model).toHaveValue('synthetic-draft-model');
  expect(screen.getByLabelText('DeepSeek API Key（留空保留当前Key）')).toHaveValue('synthetic-draft-key');
});

it('企业身份不请求开发用户目录、不提供身份切换；失效时提供企业登录入口', async () => {
  vi.mocked(api.authConfig).mockResolvedValue({ authentication: 'sso_cookie', mode: 'mock', login_url: '/sso/login', logout_url: '/sso/logout' });
  vi.mocked(api.me).mockResolvedValue({ user: { ...admin, role: 'MANAGER' }, authentication: 'sso_cookie', mode: 'mock', csrf_token: 'synthetic-csrf' });
  const view = render(<MemoryRouter initialEntries={['/sync']}><App /></MemoryRouter>);
  await screen.findByText('仅管理员可以访问同步中心');
  expect(screen.queryByRole('combobox', { name: '开发模拟身份' })).toBeNull();
  expect(api.devUsers).not.toHaveBeenCalled();
  view.unmount();
  vi.mocked(api.me).mockRejectedValue(new Error('synthetic expired session'));
  render(<MemoryRouter><App /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('link', { name: '企业登录' })).toHaveAttribute('href', '/sso/login'));
  expect(screen.queryByRole('button', { name: '恢复默认开发身份' })).toBeNull();
});
