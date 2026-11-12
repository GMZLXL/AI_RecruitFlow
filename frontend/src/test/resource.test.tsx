import { useCallback } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useResource } from '../features/shared/useResource';
import { filterParams } from '../features/recruitment/filters';

describe('请求与日期边界', () => {
  it('筛选变化后丢弃旧请求结果', async () => {
    let first!: (value: string) => void;
    const old = new Promise<string>(resolve => { first = resolve; });
    const hook = renderHook(({ current }) => useResource(useCallback(() => current === 1 ? old : Promise.resolve('new'), [current])), { initialProps: { current: 1 } });
    hook.rerender({ current: 2 });
    await waitFor(() => expect(hook.result.current.data).toBe('new'));
    await act(async () => { first('old'); await old; });
    expect(hook.result.current.data).toBe('new');
  });
  it('日期区间跨闰日和年末使用上海午夜与半开区间', () => {
    expect(filterParams({ start: '2024-02-28', end: '2024-02-29' })).toMatchObject({ from: '2024-02-28T00:00:00+08:00', to: '2024-03-01T00:00:00+08:00' });
    expect(filterParams({ end: '2026-12-31' }).to).toBe('2027-01-01T00:00:00+08:00');
  });
});
