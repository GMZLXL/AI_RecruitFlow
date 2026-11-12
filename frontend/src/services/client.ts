import axios from 'axios';
import type { components } from '../types/api.generated';
type Schemas = components['schemas'];
export const client = axios.create({ baseURL: '/api/v1', timeout: 12000 });
let authentication: 'development_only' | 'sso_cookie' | null = null;
let csrf: string | null = null;
export function configureAuthentication(mode: 'development_only' | 'sso_cookie') { authentication = mode; csrf = null; }
export function configureCsrf(token: string | null) { csrf = token; }
client.interceptors.request.use(request => {
  if (authentication === 'development_only') request.headers.set('X-Dev-User', sessionStorage.getItem('recruitflow.dev_user') || 'admin');
  else request.headers.delete('X-Dev-User');
  if (authentication === 'sso_cookie' && csrf && !['get', 'head', 'options'].includes(request.method ?? 'get')) request.headers.set('X-CSRF-Token', csrf);
  else request.headers.delete('X-CSRF-Token');
  return request;
});

export function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<Schemas['ErrorResponse']>(error)) {
    return error.response?.data.error?.message ?? fallback;
  }
  return fallback;
}
