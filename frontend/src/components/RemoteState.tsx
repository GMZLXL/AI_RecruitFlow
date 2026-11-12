import { Alert, Button, Empty, Skeleton } from 'antd';

export function LoadState() { return <div role="status" aria-label="正在加载"><Skeleton active paragraph={{ rows: 5 }} /></div>; }
export function ErrorState({ error, retry }: { error: string; retry: () => void }) {
  return <Alert type="error" showIcon message={error} action={<Button onClick={retry}>重新加载</Button>} />;
}
export function EmptyState({ description = '当前筛选下暂无记录' }: { description?: string }) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />;
}
