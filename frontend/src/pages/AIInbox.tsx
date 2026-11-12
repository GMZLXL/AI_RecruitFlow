import { useState } from 'react';
import { Alert, Button, Card, Col, Input, Row, Tag, Typography, message } from 'antd';
import { api, type IngestResult } from '../services/api';
import PageHead from '../components/PageHead';
import { STAGES } from '../features/recruitment/presentation';
const { Text, Paragraph } = Typography;
export default function AIInbox() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const submit = async () => {
    setBusy(true); setResult(null);
    try { setResult(await api.ingest(text)); message.info('Mock 解析结束；真实 DeepSeek 接入见开发任务 S2'); }
    catch { message.error('处理失败，请检查后端运行状态'); }
    finally { setBusy(false); }
  };
  return <>
    <PageHead title="AI 消息录入" desc="支持明确新增；阶段更新须先人工推进到一面，再输入申请编号 + 一面通过。完整Parser与审核在S2实施。" />
    <Row gutter={[16,16]}>
      <Col xs={24} lg={13}><Card title="粘贴招聘业务消息"><Input.TextArea rows={7} maxLength={2000} showCount placeholder="例如：新增张三应聘数据分析岗" value={text} onChange={e=>setText(e.target.value)} /><Button block type="primary" loading={busy} disabled={!text.trim()} style={{marginTop:22}} onClick={() => void submit()}>解析并处理</Button></Card></Col>
      <Col xs={24} lg={11}><Card title="AI 处理结果" style={{minHeight:285}}>{!result ? <Text type="secondary">提交后在此展示系统处理状态。</Text> : <>
        <Alert showIcon type={result.status==='applied'?'success':result.status==='needs_confirmation'?'warning':'info'} message={result.status==='applied'?'本地业务记录处理成功':result.status==='needs_confirmation'?'需要人工确认':result.status==='duplicate'?'重复事件':'处理结果'} description={result.reason || result.intent || ''} />
        {result.application && <Paragraph style={{marginTop:12}}>申请：{result.application.application_code}<br/>候选人：{result.application.candidate_name}<br/>当前阶段：{STAGES[result.application.stage]}<br/>腾讯文档：<Tag>待模拟同步</Tag></Paragraph>}
        {result.status==='needs_confirmation' && <Text type="secondary">完整的待确认队列、候选人匹配和编辑界面将在 Codex S2/S4 完成。</Text>}
      </>}</Card></Col>
    </Row>
    <Alert className="section-card" type="warning" showIcon message="本页面是本地 Mock 演示，不会调用 DeepSeek，也不会向腾讯文档或企业微信发送任何数据。" />
  </>;
}
