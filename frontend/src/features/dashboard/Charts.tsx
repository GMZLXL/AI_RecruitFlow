import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, FunnelChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, AriaComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Card, Col, Row } from 'antd';
import type { DashboardData } from '../../services/api';
import { STAGES } from '../recruitment/presentation';
import { EmptyState } from '../../components/RemoteState';
echarts.use([BarChart, LineChart, FunnelChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);

export default function Charts({ data }: { data: DashboardData }) {
  const stageData = Object.entries(STAGES).map(([stage, name]) => ({ name, value: data.by_stage[stage as keyof typeof STAGES] ?? 0 }));
  const base = { aria: { enabled: true }, animation: false, color: ['#1677ff', '#3b8c76'], tooltip: { trigger: 'axis' } };
  return <Row gutter={[16, 16]} className="section-card">
    <Col xs={24} xl={12}><Card title="当前阶段分布" extra="申请维度">
      <p className="chart-note">各阶段为当前快照分布，不是历史转化率。</p>
      {data.new_applications ? <ReactEChartsCore echarts={echarts} option={{ ...base, tooltip: { trigger: 'item' }, series: [{ type: 'funnel', sort: 'none', left: '12%', width: '65%', top: 10, bottom: 10, minSize: '8%', label: { formatter: '{b}：{c}' }, data: stageData }] }} style={{ height: 300 }} /> : <EmptyState description="所选范围暂无招聘申请" />}
    </Card></Col>
    <Col xs={24} xl={12}><Card title="每周新增申请" extra="上海时间 · 周一开始">
      <p className="chart-note">依据申请创建日期聚合，筛选范围外的申请不计入。</p>
      {data.weekly_new.length ? <ReactEChartsCore echarts={echarts} option={{ ...base, grid: { left: 40, right: 15, top: 25, bottom: 45 }, xAxis: { type: 'category', data: data.weekly_new.map(row => row.week) }, yAxis: { type: 'value', minInterval: 1 }, series: [{ type: 'line', data: data.weekly_new.map(row => row.count), smooth: false }] }} style={{ height: 300 }} /> : <EmptyState description="暂无新增申请趋势" />}
    </Card></Col>
    <Col xs={24}><Card title="岗位招聘进度"><p className="chart-note">蓝色为申请量，绿色为已录用量；编制在下方显示，不把申请量当作完成率。</p>
      {data.by_position.length ? <><ReactEChartsCore echarts={echarts} option={{ ...base, grid: { left: 115, right: 25, top: 10, bottom: 30 }, yAxis: { type: 'category', data: data.by_position.map(row => row.title), axisLabel: { width: 95, overflow: 'truncate' } }, xAxis: { type: 'value', minInterval: 1 }, series: [{ name: '申请量', type: 'bar', data: data.by_position.map(row => row.applications) }, { name: '已录用', type: 'bar', data: data.by_position.map(row => row.hired) }] }} style={{ height: Math.max(220, data.by_position.length * 48) }} />
        <ul className="position-summary">{data.by_position.map(row => <li key={row.position_id}>{row.title}：已录用 {row.hired} / 编制 {row.target_headcount}，申请 {row.applications}</li>)}</ul></> : <EmptyState description="暂无岗位进展" />}
    </Card></Col>
  </Row>;
}
