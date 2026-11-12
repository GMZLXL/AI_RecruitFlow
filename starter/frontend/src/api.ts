import axios from 'axios';
import type { components, operations } from './types/api.generated';

type Schemas = components['schemas'];
export type Application = Schemas['ApplicationRead'];
export type Stage = Schemas['Stage'];
export type ApplicationCreate = Schemas['ApplicationCreate'];
export type SyncJob = Schemas['SyncJob'];
export type DashboardData = Schemas['DashboardData'];
export type IngestResult = Schemas['IngestionResult'];
export type Pagination = Schemas['Pagination'];
export type User = Schemas['UserRead'];
type MeResponse = operations['me_api_v1_me_get']['responses'][200]['content']['application/json'];
type UsersResponse = operations['development_users_api_v1_dev_users_get']['responses'][200]['content']['application/json'];
type PatchResponse = operations['application_patch_api_v1_applications__application_id__patch']['responses'][200]['content']['application/json'];
type ApplicationList = operations['applications_api_v1_applications_get']['responses'][200]['content']['application/json'];
type SyncList = operations['sync_jobs_api_v1_sync_jobs_get']['responses'][200]['content']['application/json'];
type CreateResponse = operations['create_application_api_v1_applications_post']['responses'][201]['content']['application/json'];
type DashboardResponse = operations['dashboard_api_v1_dashboard_overview_get']['responses'][200]['content']['application/json'];
type IngestResponse = operations['ingestion_api_v1_ingestions_post']['responses'][200]['content']['application/json'];
type SyncResponse = operations['run_mock_sync_api_v1_sync_run_post']['responses'][200]['content']['application/json'];

export const client = axios.create({ baseURL: '/api/v1', timeout: 12000 });
client.defaults.headers.common['X-Dev-User'] = sessionStorage.getItem('recruitflow.dev_user') || 'admin';

export function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<Schemas['ErrorResponse']>(error)) {
    return error.response?.data.error?.message ?? fallback;
  }
  return fallback;
}

export const api = {
  me: async () => (await client.get<MeResponse>('/me')).data.data,
  devUsers: async () => (await client.get<UsersResponse>('/dev/users')).data.data,
  selectDevUser: (id: string) => { sessionStorage.setItem('recruitflow.dev_user', id); window.location.reload(); },
  applications: async (page = 1, page_size = 8) =>
    (await client.get<ApplicationList>('/applications', { params: { page, page_size } })).data,
  addApplication: async (data: ApplicationCreate) =>
    (await client.post<CreateResponse>('/applications', data, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  dashboard: async () => (await client.get<DashboardResponse>('/dashboard/overview')).data.data,
  advance: async (application: Application, stage: Stage) => (await client.patch<PatchResponse>(`/applications/${application.id}`, {
    stage, change_reason: 'Web 人工推进招聘阶段',
  } satisfies Schemas['ApplicationPatch'], { headers: { 'If-Match': application.version, 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  ingest: async (text: string) => (await client.post<IngestResponse>('/ingestions', {
    text, source: 'manual', external_event_id: crypto.randomUUID(),
  } satisfies Schemas['IngestionRequest'])).data.data,
  syncJobs: async (page = 1, page_size = 8) =>
    (await client.get<SyncList>('/sync/jobs', { params: { page, page_size } })).data,
  runMockSync: async () => (await client.post<SyncResponse>('/sync/run', {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data.data,
};
