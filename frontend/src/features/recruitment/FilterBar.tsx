import { useCallback } from 'react';
import { Button, Form, Input, Select, Space } from 'antd';
import { api } from '../../services/api';
import { useResource } from '../shared/useResource';
import { STAGES } from './presentation';
import type { Filters } from './filters';

export default function FilterBar({ initial = {}, onSearch, search = false, dates = true, stages = true, referenceDates = false }: {
  initial?: Filters; onSearch: (value: Filters) => void; search?: boolean; dates?: boolean; stages?: boolean; referenceDates?: boolean;
}) {
  const options = useResource(useCallback((signal: AbortSignal) => api.options('', signal), []));
  const [form] = Form.useForm<Filters>();
  return <Form form={form} layout="vertical" initialValues={initial} onFinish={onSearch} className="filter-bar">
    {search && <Form.Item name="keyword" label="姓名或申请编号"><Input allowClear maxLength={120} /></Form.Item>}
    {search && <Form.Item name="source_channel" label="来源渠道"><Input allowClear maxLength={100} placeholder="例如：演示样本" /></Form.Item>}
    <Form.Item name="position_id" label="岗位"><Select allowClear showSearch optionFilterProp="label" loading={options.loading}
      placeholder={options.error ? '岗位读取失败，请刷新页面' : '全部岗位'} options={options.data?.positions.map(row => ({ value: row.id, label: row.title }))} /></Form.Item>
    <Form.Item name="owner_id" label="负责人"><Select allowClear placeholder="全部负责人" options={options.data?.owners.map(row => ({ value: row.id, label: row.display_name }))} /></Form.Item>
    {stages && <Form.Item name="stage" label="阶段"><Select allowClear placeholder="全部阶段" options={Object.entries(STAGES).map(([value, label]) => ({ value, label }))} /></Form.Item>}
    {dates && <><Form.Item name="start" label={referenceDates ? '参考时间起日（上海）' : '申请创建起日（上海）'}><Input type="date" /></Form.Item>
      <Form.Item name="end" label={referenceDates ? '参考时间止日（含当天）' : '申请创建止日（含当天）'} dependencies={['start']} rules={[({ getFieldValue }) => ({ validator(_, value) {
        return !value || !getFieldValue('start') || value >= getFieldValue('start') ? Promise.resolve() : Promise.reject(new Error('止日不能早于起日'));
      } })]}><Input type="date" /></Form.Item></>}
    <Form.Item className="filter-actions" label="操作"><Space><Button type="primary" htmlType="submit">查询</Button><Button onClick={() => { form.resetFields(); onSearch(initial); }}>重置</Button></Space></Form.Item>
  </Form>;
}
