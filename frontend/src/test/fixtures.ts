import type { Application, DashboardData, User } from '../services/api';

export const admin: User = { id: '00000000-0000-0000-0000-000000000001', display_name: '模拟管理员', role: 'ADMIN', department: 'engineering', active: true, version: 1, created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' };
export const application: Application = {
  id: '00000000-0000-0000-0000-000000000002', application_code: 'DEMO_TEST_01', candidate_id: '00000000-0000-0000-0000-000000000003',
  candidate_name: '林沐（虚构）', position_id: '00000000-0000-0000-0000-000000000004', position_title: '前端工程师（演示）',
  owner_id: admin.id, owner_name: admin.display_name, source_channel: '演示样本', stage: 'applied', outcome: 'pending', custom_fields: {},
  version: 1, created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-12T00:00:00Z', sync_status: 'pending',
};
export const emptyDashboard: DashboardData = {
  new_applications: 0, candidates: 0, upcoming_interviews: 0, pending_feedback: 0, offers_sent: 0, offers_accepted: 0,
  offers_declined: 0, offer_acceptance_rate: null, hired_applications: 0, by_stage: {}, weekly_new: [], by_position: [], pending_sync: 0,
  mode: 'mock', timezone: 'Asia/Shanghai', population: '基于真实数据库记录',
};
export const list = <T,>(data: T[], total = data.length) => ({ data, request_id: 'synthetic-request', pagination: { page: 1, page_size: 8, total } });
