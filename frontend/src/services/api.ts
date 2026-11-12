import { client } from './client';
export { errorMessage } from './client';
import type { components, operations } from '../types/api.generated';

type Schemas = components['schemas'];
export type ApplicationFilters = NonNullable<operations['applications_api_v1_applications_get']['parameters']['query']>;
export type TaskFilters = NonNullable<operations['tasks_api_v1_tasks_get']['parameters']['query']>;
export type Position = Schemas['PositionRead'];
export type PositionCreate = Schemas['PositionCreate'];
export type Interview = Schemas['InterviewRead'];
export type InterviewCreate = Schemas['InterviewCreate'];
export type InterviewPatch = Schemas['InterviewPatch'];
export type ApplicationPatch = Schemas['ApplicationPatch'];
export type Offer = Schemas['OfferRead'];
export type OfferCreate = Schemas['OfferCreate'];
export type OfferPatch = Schemas['OfferPatch'];
export type Options = Schemas['RecruitmentOptions'];
export type Task = Schemas['TaskRead'];
export type History = Schemas['HistoryRead'];
export type Application = Schemas['ApplicationRead'];
export type Stage = Schemas['Stage'];
export type ApplicationCreate = Schemas['ApplicationCreate'];
export type SyncJob = Schemas['SyncJob'];
export type SyncState = Schemas['SyncState'];
export type SyncSummary = Schemas['SyncSummary'];
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
type SyncResponse = operations['run_mock_sync_api_v1_sync_run_post']['responses'][202]['content']['application/json'];
type SyncSummaryResponse = operations['sync_summary_api_v1_sync_summary_get']['responses'][200]['content']['application/json'];
type RetrySyncResponse = operations['retry_sync_api_v1_sync_jobs__job_id__retry_post']['responses'][200]['content']['application/json'];
type DetailResponse = operations['application_detail_api_v1_applications__application_id__get']['responses'][200]['content']['application/json'];
type OptionsResponse = operations['recruitment_options_api_v1_recruitment_options_get']['responses'][200]['content']['application/json'];
type TasksResponse = operations['tasks_api_v1_tasks_get']['responses'][200]['content']['application/json'];
type HistoryResponse = operations['application_history_api_v1_applications__application_id__history_get']['responses'][200]['content']['application/json'];
type InterviewsResponse = operations['interviews_api_v1_applications__application_id__interviews_get']['responses'][200]['content']['application/json'];
type NewInterviewResponse = operations['interview_create_api_v1_applications__application_id__interviews_post']['responses'][201]['content']['application/json'];
type PatchInterviewResponse = operations['interview_patch_api_v1_interviews__interview_id__patch']['responses'][200]['content']['application/json'];
type OfferResponse = operations['application_offer_api_v1_applications__application_id__offer_get']['responses'][200]['content']['application/json'];
type NewOfferResponse = operations['offer_create_api_v1_applications__application_id__offer_post']['responses'][201]['content']['application/json'];
type PatchOfferResponse = operations['offer_patch_api_v1_applications__application_id__offer_patch']['responses'][200]['content']['application/json'];
type PositionsResponse = operations['positions_api_v1_positions_get']['responses'][200]['content']['application/json'];
type NewPositionResponse = operations['position_create_api_v1_positions_post']['responses'][201]['content']['application/json'];
type CandidatesResponse = operations['candidates_api_v1_candidates_get']['responses'][200]['content']['application/json'];
type PolicyResponse = operations['settings_policy_api_v1_settings_policy_get']['responses'][200]['content']['application/json'];
type IntegrationsResponse = operations['integration_status_api_v1_integrations_status_get']['responses'][200]['content']['application/json'];

export const api = {
  me: async () => (await client.get<MeResponse>('/me')).data.data,
  devUsers: async () => (await client.get<UsersResponse>('/dev/users')).data.data,
  selectDevUser: (id: string) => { sessionStorage.setItem('recruitflow.dev_user', id); window.location.reload(); },
  applications: async (page = 1, page_size = 8, keyword = '', filters: ApplicationFilters = {}, signal?: AbortSignal) =>
    (await client.get<ApplicationList>('/applications', { params: { ...filters, page, page_size, keyword: keyword.trim() || undefined }, signal })).data,
  addApplication: async (data: ApplicationCreate, key = crypto.randomUUID()) =>
    (await client.post<CreateResponse>('/applications', data, { headers: { 'Idempotency-Key': key } })).data.data,
  dashboard: async (filters: Pick<ApplicationFilters, 'from' | 'to' | 'position_id' | 'owner_id' | 'stage'> = {}, signal?: AbortSignal) => (await client.get<DashboardResponse>('/dashboard/overview', { params: filters, signal })).data.data,
  application: async (id: string, signal?: AbortSignal) => (await client.get<DetailResponse>(`/applications/${id}`, { signal })).data.data,
  options: async (keyword = '', signal?: AbortSignal) => (await client.get<OptionsResponse>('/recruitment/options', { params: { keyword }, signal })).data.data,
  tasks: async (params: TaskFilters = {}, signal?: AbortSignal) => (await client.get<TasksResponse>('/tasks', { params, signal })).data,
  history: async (id: string, page = 1, signal?: AbortSignal) => (await client.get<HistoryResponse>(`/applications/${id}/history`, { params: { page, page_size: 8 }, signal })).data,
  interviews: async (id: string, page = 1, signal?: AbortSignal) => (await client.get<InterviewsResponse>(`/applications/${id}/interviews`, { params: { page, page_size: 8 }, signal })).data,
  updateApplication: async (row: Application, data: ApplicationPatch, key: string) => (await client.patch<PatchResponse>(`/applications/${row.id}`, data, { headers: { 'If-Match': row.version, 'Idempotency-Key': key } })).data.data,
  createInterview: async (row: Application, data: InterviewCreate, key: string) => (await client.post<NewInterviewResponse>(`/applications/${row.id}/interviews`, data, { headers: { 'If-Match': row.version, 'Idempotency-Key': key } })).data.data,
  updateInterview: async (row: Interview, data: InterviewPatch, key: string) => (await client.patch<PatchInterviewResponse>(`/interviews/${row.id}`, data, { headers: { 'If-Match': row.version, 'Idempotency-Key': key } })).data.data,
  offer: async (id: string, signal?: AbortSignal) => (await client.get<OfferResponse>(`/applications/${id}/offer`, { signal })).data.data,
  createOffer: async (row: Application, data: OfferCreate, key: string) => (await client.post<NewOfferResponse>(`/applications/${row.id}/offer`, data, { headers: { 'If-Match': row.version, 'Idempotency-Key': key } })).data.data,
  respondOffer: async (id: string, row: Offer, data: OfferPatch, key: string) => (await client.patch<PatchOfferResponse>(`/applications/${id}/offer`, data, { headers: { 'If-Match': row.version, 'Idempotency-Key': key } })).data.data,
  positions: async (page = 1, signal?: AbortSignal) => (await client.get<PositionsResponse>('/positions', { params: { page, page_size: 8 }, signal })).data,
  createPosition: async (data: PositionCreate, key: string) => (await client.post<NewPositionResponse>('/positions', data, { headers: { 'Idempotency-Key': key } })).data.data,
  candidates: async (keyword = '') => (await client.get<CandidatesResponse>('/candidates', { params: { keyword, page_size: 100 } })).data,
  policy: async (signal?: AbortSignal) => (await client.get<PolicyResponse>('/settings/policy', { signal })).data.data,
  integrations: async (signal?: AbortSignal) => (await client.get<IntegrationsResponse>('/integrations/status', { signal })).data.data,
  advance: async (application: Application, stage: Stage) => (await client.patch<PatchResponse>(`/applications/${application.id}`, {
    stage, change_reason: 'Web 人工推进招聘阶段',
  } satisfies Schemas['ApplicationPatch'], { headers: { 'If-Match': application.version, 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  ingest: async (text: string, eventId: string) => (await client.post<IngestResponse>('/ingestions', {
    text, source: 'manual', external_event_id: eventId, execute_if_unambiguous: true,
  } satisfies Schemas['IngestionRequest'], { timeout: 130000 })).data.data,
  confirmations: async (page = 1) => (await client.get<ConfirmationsResponse>('/confirmations', { params: { page, page_size: 8 } })).data,
  resolve: async (row: Confirmation, data: ResolveRequest) => (await client.post<ResolveResponse>(`/confirmations/${row.id}/resolve`, data,
    { headers: { 'If-Match': row.version, 'Idempotency-Key': crypto.randomUUID() } })).data.data,
  syncJobs: async (page = 1, page_size = 8, status?: SyncState, signal?: AbortSignal) =>
    (await client.get<SyncList>('/sync/jobs', { params: { page, page_size, status }, signal })).data,
  syncSummary: async (signal?: AbortSignal) => (await client.get<SyncSummaryResponse>('/sync/summary', { signal })).data.data,
  retrySync: async (row: SyncJob, reason: string, key: string) => (await client.post<RetrySyncResponse>(`/sync/jobs/${row.id}/retry`,
    { reason } satisfies Schemas['SyncRetry'], { headers: { 'If-Match': row.revision, 'Idempotency-Key': key } })).data.data,
  runMockSync: async () => (await client.post<SyncResponse>('/sync/run', {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data.data,
};
