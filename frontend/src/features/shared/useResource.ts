import { useCallback, useEffect, useState } from 'react';
import { errorMessage } from '../../services/api';

export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    const run = async () => {
      setLoading(true); setError(''); setData(null);
      try { const value = await loader(controller.signal); if (!controller.signal.aborted) setData(value); }
      catch (cause) { if (!controller.signal.aborted) setError(errorMessage(cause, '读取失败，请检查连接并重试')); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void run();
    return () => controller.abort();
  }, [loader, revision]);
  return { data, loading, error, reload };
}
