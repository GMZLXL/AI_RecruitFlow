import type { Stage } from '../../services/api';
export const STAGES: Record<Stage, string> = { applied: '新申请', screening: '简历筛选', interview_1: '一面', interview_2: '二面', offer: 'Offer阶段', hired: '录用', rejected: '淘汰/结束', withdrawn: '主动退出' };
export const stageLabel = (stage: string) => STAGES[stage as Stage] ?? stage;
export const formatTime = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
export const NEXT_STAGE: Partial<Record<Stage, Stage>> = { applied: 'screening', screening: 'interview_1', interview_1: 'interview_2', interview_2: 'offer' };
