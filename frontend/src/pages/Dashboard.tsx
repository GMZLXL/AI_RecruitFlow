import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Row, Statistic, Typography } from 'antd';
import { api, type DashboardData } from '../services/api';
import PageHead from '../components/PageHead';
import ReactECharts from 'echarts-for-react';
import { stageLabel } from '../features/recruitment/presentation';
const { Text } = Typography;
export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => { try { setError(''); setData(await api.dashboard()); } catch { setError('无法连接后端，请确认 FastAPI 已启动。'); } }, []);
  useEffect(() => { void load(); }, [load]);
  const chart = useMemo(() => ({
    tooltip: { trigger: 'axis' }, grid: { left: 40, right: 20, top: 25, bottom: 40 },
    xAxis: { type: 'category', data: Object.keys(data?.by_stage || {}).map(stageLabel) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', barWidth: 45, data: Object.values(data?.by_stage || {}), itemStyle: { color: '#1677ff', borderRadius: [6, 6, 0, 0] } }]
  }), [data]);
  return <>
    <PageHead title="招聘工作台" desc="招聘数据直接来自本地数据库，演示环境不连接真实腾讯文档。" />
    {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} />}
    <Row gutter={[16,16]}>
      <Col xs={24} md={8}><Card><Statistic title="招聘申请总数" value={data?.new_applications ?? '—'} /></Card></Col>
      <Col xs={24} md={8}><Card><Statistic title="等待模拟同步" value={data?.pending_sync ?? '—'} /></Card></Col>
      <Col xs={24} md={8}><Card><Statistic title="运行环境" value="Mock" valueStyle={{fontSize: 23}} /></Card></Col>
    </Row>
    <Card className="section-card" title="招聘阶段分布" extra={<Button onClick={() => void load()}>刷新</Button>}>
      {!data || Object.keys(data.by_stage).length === 0 ? <Text type="secondary">暂无申请数据，可在“候选人记录”或“AI录入”新增演示记录。</Text> : <ReactECharts option={chart} style={{height:320}} />}
    </Card>
  </>;
}
