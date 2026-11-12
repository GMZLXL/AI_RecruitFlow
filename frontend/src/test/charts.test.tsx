import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Charts from '../features/dashboard/Charts';
import { emptyDashboard } from './fixtures';

vi.mock('echarts-for-react/lib/core', () => ({ default: () => <div data-testid="actual-chart" /> }));
it('空库展示三个明确空态，不创建示例图形', () => {
  render(<Charts data={emptyDashboard} />);
  expect(screen.getByText('所选范围暂无招聘申请')).toBeInTheDocument();
  expect(screen.getByText('暂无新增申请趋势')).toBeInTheDocument();
  expect(screen.getByText('暂无岗位进展')).toBeInTheDocument();
  expect(screen.queryByTestId('actual-chart')).not.toBeInTheDocument();
});
