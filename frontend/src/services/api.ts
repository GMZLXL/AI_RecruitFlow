import { client } from './client';
export { errorMessage } from './client';
import type { components, operations } from '../types/api.generated';

type Schemas = components['schemas'];
export type Application = Schemas['ApplicationRead'];
export type Stage = Schemas['Stage'];
export type ApplicationCreate = Schemas['ApplicationCreate'];
export type SyncJob = Schemas['SyncJob'];
export type DashboardData = Schemas['DashboardData'];
export type IngestResult = Schemas['IngestionResult'];
export type Pagination = Schemas['Pagination'];
export type User = Schemas['UserRead'];
export type Confirmation = Schemas['ConfirmationRead'];
export type Extraction = Schemas['Extraction'];
export type ResolveRequest = Schemas['ResolveRequest'];
export type Resolution = Schemas['ResolutionResult'];
type ConfirmationsResponse = operations['confirmations_api_v1_confirmations_get']['responses'][200]['content']['application/json'];
type ResolveResponse = operations['confirmation_resolve_api_v1_confirmations__confirmation_id__resolve_post']['responses'][200]['content']['application/json'];
type MeResponse = operations['me_api_v1_me_get']['responses'][200]['content']['application/json'];
type UsersResponse = operations['development_users_api_v1_dev_users_get']['responses'][200]['content']['application/json'];
type PatchResponse = operations['application_patch_api_v1_applications__application_id__patch']['responses'][200]['content']['application/json'];
type ApplicationList = operations['applications_api_v1_applications_get']['responses'][200]['content']['application/json'];
type SyncList = operations['sync_jobs_api_v1_sync_jobs_get']['responses'][200]['content']['application/json'];
type CreateResponse = operations['create_application_api_v1_applications_post']['responses'][201]['content']['application/json'];
type DashboardResponse = operations['dashboard_api_v1_dashboard_overview_get']['responses'][200]['content']['application/json'];
type IngestResponse = operations['ingestion_api_v1_ingestions_post']['responses'][200]['content']['application/json'];
type SyncResponse = operations['run_mock_sync_api_v1_sync_run_post']['responses'][200]['content']['application/json'];

export const api = {
  me: async () => (await client.get<MeResponse>('/me')).data.data,
  devUsers: async () => (await client.get<UsersResponse>('/dev/users')).data.data,
  selectDevUser: (id: string) => { sessionStorage.setItem('recruitflow.dev_user', id); window.location.reload(); },
  applications: async (page = 1, page_size = 8, keyword = '') =>
    (await client.get<ApplicationList>('/applications', { params: { page, page_size, keyword: keyword || undefined } })).data,
  addApplication: async (data: ApplicationCreate) =>
    (await client.post<CreateResponse>('/applications', data, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  dashboard: async () => (await client.get<DashboardResponse>('/dashboard/overview')).data.data,
  advance: async (application: Application, stage: Stage) => (await client.patch<PatchResponse>(`/applications/${application.id}`, {
    stage, change_reason: 'Web 人工推进招聘阶段',
  } satisfies Schemas['ApplicationPatch'], { headers: { 'If-Match': application.version, 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  ingest: async (text: string, eventId: string) => (await client.post<IngestResponse>('/ingestions', {
    text, source: 'manual', external_event_id: eventId, execute_if_unambiguous: true,
  } satisfies Schemas['IngestionRequest'], { timeout: 130000 })).data.data,
  confirmations: async (page = 1) => (await client.get<ConfirmationsResponse>('/confirmations', { params: { page, page_size: 8 } })).data,
  resolve: async (row: Confirmation, data: ResolveRequest) => (await client.post<ResolveResponse>(`/confirmations/${row.id}/resolve`, data,
    { headers: { 'If-Match': row.version, 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  syncJobs: async (page = 1, page_size = 8) =>
    (await client.get<SyncList>('/sync/jobs', { params: { page, page_size } })).data,
  runMockSync: async () => (await client.post<SyncResponse>('/sync/run', {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data.data,
};
