import { Tag } from 'antd';
import { STAGES } from './presentation';
import { SYNC_STATES } from '../sync/presentation';
import type { Stage, SyncState } from '../../services/api';

export function StageTag({ stage }: { stage: Stage }) { return <Tag color={stage === 'hired' ? 'green' : stage === 'rejected' ? 'default' : 'blue'}>{STAGES[stage]}</Tag>; }
export function SyncTag({ status }: { status?: SyncState | null }) { const info = status ? SYNC_STATES[status] : null; return <Tag color={info?.color}>{info?.label ?? '暂无投影任务'}</Tag>; }
