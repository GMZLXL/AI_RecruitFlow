import { Card, Typography } from 'antd';
import PageHead from './PageHead';
const { Text } = Typography;
export default function FeaturePending({ title }: {title:string}) { return <><PageHead title={title} desc="属于完整 MVP 设计范围；请用 docs/02 与 codex/PHASE_TASKS.md 指导 Codex 继续开发。"/><Card><Text type="secondary">当前 Starter 只提供基础演示。完整身份权限、面试管理、人工审核、企微回调与生产部署尚未实现。</Text></Card></>; }
