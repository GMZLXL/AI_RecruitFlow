import { useCallback, useState } from 'react';
import { Alert, Button, Card, Checkbox, Form, Input, Select } from 'antd';
import { api, errorMessage, type AISettingsUpdate } from '../../services/api';
import { useResource } from '../shared/useResource';
import { ErrorState, LoadState } from '../../components/RemoteState';

export default function AISettingsPanel({ onSaved }: { onSaved: () => void }) {
  const settings = useResource(useCallback((signal: AbortSignal) => api.aiSettings(signal), []), { keepPreviousData: true });
  const [form] = Form.useForm<AISettingsUpdate>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  return <Card className="section-card" title="AI 接入配置" extra={<Button aria-label="刷新AI配置，保留草稿" loading={settings.loading} disabled={busy} onClick={settings.reload}>刷新配置</Button>}>
    {settings.error && <ErrorState error={settings.error} retry={settings.reload} />}
    {!settings.data ? settings.loading && <LoadState /> : <>
      <p>API Key：{settings.data.has_api_key ? '已配置' : '未配置'}{settings.data.key_source === 'environment' ? '（来自服务器环境）' : settings.data.key_source === 'managed' ? '（已加密保存）' : ''}。已保存的密钥不会回显；仅用于后端调用 DeepSeek 官方接口。</p>
      <p className="chart-note">最新保存：{settings.data.provider === 'mock' ? 'Mock规则' : 'DeepSeek'} · {settings.data.model || '未指定模型'}（版本{settings.data.version}）。刷新保留草稿，请核对后保存。保存配置不代表联通验证通过。</p>
      {!settings.data.real_calls_allowed && <Alert type="info" showIcon message="当前为模拟环境，可先保存Key与模型并保持Mock；启用DeepSeek需管理员允许真实AI调用。" />}
      {!settings.data.secret_store_ready && <Alert type="warning" showIcon message="服务端加密存储尚未就绪，请管理员配置主密钥后再保存API Key。" />}
      {error && <Alert type="error" showIcon message={error} />}
      {success && <div role="status"><Alert type="success" showIcon message={success} /></div>}
      <Form name="ai-settings" className="compact-form" form={form} layout="vertical"
        initialValues={{ provider: settings.data.provider, model: settings.data.model, clear_api_key: false, change_reason: '管理员更新AI接入配置' }}
        onValuesChange={() => { setKey(crypto.randomUUID()); setSuccess(''); }} onFinish={async value => {
          setBusy(true); setError(''); setSuccess('');
          try {
            const saved = await api.updateAISettings(settings.data!, { ...value, api_key: value.clear_api_key ? null : value.api_key?.trim() || null }, key);
            form.setFieldsValue({ api_key: '', clear_api_key: false });
            setSuccess(`AI配置已保存（版本${saved.version}），${saved.has_api_key ? 'Key已配置' : '未配置Key'}；${saved.provider === 'mock' ? '当前使用Mock' : 'DeepSeek尚未验证联通'}`);
            settings.reload(); onSaved(); setKey(crypto.randomUUID());
          } catch (cause) { setError(errorMessage(cause, '保存失败，请保留草稿重试；版本冲突时先刷新配置并核对')); }
          finally { setBusy(false); }
        }}>
        <Form.Item name="provider" label="解析方式" rules={[{ required: true }]}><Select options={[{ value: 'mock', label: 'Mock规则（不调用外部模型）' }, { value: 'deepseek', label: 'DeepSeek API', disabled: !settings.data.real_calls_allowed }]} /></Form.Item>
        <Form.Item name="model" label="模型名称" rules={[{ required: true, whitespace: true }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '请填写模型标识，使用字母、数字、点、下划线或短横线' }]}><Input maxLength={120} autoComplete="off" placeholder="填写账户可用的DeepSeek模型名" /></Form.Item>
        <Form.Item name="api_key" label="DeepSeek API Key（留空保留当前Key）"><Input.Password visibilityToggle={false} autoComplete="off" maxLength={512} disabled={!settings.data.secret_store_ready} /></Form.Item>
        <Form.Item name="clear_api_key" valuePropName="checked"><Checkbox>清除当前Key及环境变量回退（需使用Mock）</Checkbox></Form.Item>
        <Form.Item name="change_reason" label="变更说明" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
        <Button type="primary" htmlType="submit" aria-label="保存AI配置" loading={busy} disabled={settings.loading || !!settings.error}>保存AI配置</Button>
      </Form>
    </>}
  </Card>;
}
