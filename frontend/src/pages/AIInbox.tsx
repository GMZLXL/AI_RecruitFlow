import { useState } from 'react';
import { Alert, Button, Card, Col, Input, Row, Tag, Typography, message } from 'antd';
import { api, errorMessage, type IngestResult } from '../services/api';
import PageHead from '../components/PageHead';
import { STAGES } from '../features/recruitment/presentation';
import ReviewQueue from '../features/ai/ReviewQueue';
const { Text, Paragraph } = Typography;
export default function AIInbox() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [eventId, setEventId] = useState(() => crypto.randomUUID());
  const [refreshKey, setRefreshKey] = useState(0);
  const [result, setResult] = useState<IngestResult | null>(null);
  const submit = async () => {
    setBusy(true); setResult(null);
    try { setResult(await api.ingest(text, eventId)); setRefreshKey(value=>value+1); }
    catch (error) { message.error(errorMessage(error, '处理失败，可使用原消息重试')); }
    finally { setBusy(false); }
  };
  return <>
    <PageHead title="AI 消息录入与审核" desc="解析提议经过匹配、权限和状态校验。歧义请在下方审核；同一输入重试复用事件ID，新的业务请点击新建事件。" />
    <Row gutter={[16,16]}>
      <Col xs={24} lg={13}><Card title="粘贴招聘业务消息" extra={<Button disabled={busy} onClick={()=>{setEventId(crypto.randomUUID());setText('');setResult(null);}}>新建事件</Button>}><Input.TextArea rows={7} disabled={busy} maxLength={2000} showCount placeholder="例如：新增虚构甲应聘数据分析岗" value={text} onChange={e=>{setText(e.target.value);setEventId(crypto.randomUUID());}} /><Button block type="primary" loading={busy} disabled={!text.trim()} style={{marginTop:22}} onClick={() => void submit()}>解析并处理</Button></Card></Col>
      <Col xs={24} lg={11}><Card title="AI 处理结果" style={{minHeight:285}}>{!result ? <Text type="secondary">提交后在此展示系统处理状态。</Text> : <>
        <Alert showIcon type={result.status==='applied'?'success':result.status==='needs_confirmation'?'warning':'info'} message={result.status==='applied'?'本地业务记录处理成功':result.status==='needs_confirmation'?'需要人工确认':result.status==='duplicate'?'重复事件':'处理结果'} description={result.reason || result.intent || ''} />
        {result.application && <Paragraph style={{marginTop:12}}>申请：{result.application.application_code}<br/>候选人：{result.application.candidate_name}<br/>当前阶段：{STAGES[result.application.stage]}<br/>腾讯文档：<Tag>待模拟同步</Tag></Paragraph>}
        <Paragraph>接入记录：{result.ingestion_id || '历史事件'}<br/>解析器：{result.parser_provider}<br/>原因代码：{result.reason_code || '—'}</Paragraph>
        {result.status==='needs_confirmation' && <Text type="secondary">请在下方待确认列表中审核或补全字段。</Text>}
      </>}</Card></Col>
    </Row>
    <ReviewQueue refreshKey={refreshKey} onResolved={value => setResult(current => current?.confirmation_id === value.confirmation_id ? {
      ...current, status: value.status === 'confirmed' ? 'applied' : 'failed',
      reason: value.status === 'confirmed' ? '人工审核已确认执行' : '人工审核已驳回', reason_code: undefined,
      application: value.application, application_id: value.application?.id, sync_state: value.application ? 'pending' : undefined,
    } : current)} />
    <Alert className="section-card" type="warning" showIcon message="默认Mock无网络调用；只有显式配置hybrid+DeepSeek才发送脱敏文本。腾讯文档和企业微信仍为模拟接入。" />
  </>;
}
