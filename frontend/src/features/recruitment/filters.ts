import type { ApplicationFilters } from '../../services/api';

export type Filters = Pick<ApplicationFilters, 'keyword' | 'position_id' | 'owner_id' | 'stage' | 'source_channel'> & { start?: string; end?: string };
export function nextDate(value: string) { return new Date(new Date(`${value}T00:00:00Z`).getTime() + 86400000).toISOString().slice(0, 10); }
export function filterParams(value: Filters): ApplicationFilters {
  const { start, end, ...fields } = value;
  return { ...fields, keyword: fields.keyword?.trim() || undefined, source_channel: fields.source_channel?.trim() || undefined,
    from: start ? `${start}T00:00:00+08:00` : undefined, to: end ? `${nextDate(end)}T00:00:00+08:00` : undefined };
}
export function recentDates(): Filters {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());
  return { end: today, start: new Date(new Date(`${today}T00:00:00Z`).getTime() - 29 * 86400000).toISOString().slice(0, 10) };
}
