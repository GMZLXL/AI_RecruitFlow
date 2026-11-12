import axios from 'axios';
import type { components } from '../types/api.generated';
type Schemas = components['schemas'];
export const client = axios.create({ baseURL: '/api/v1', timeout: 12000 });
client.defaults.headers.common['X-Dev-User'] = sessionStorage.getItem('recruitflow.dev_user') || 'admin';

export function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<Schemas['ErrorResponse']>(error)) {
    return error.response?.data.error?.message ?? fallback;
  }
  return fallback;
}
