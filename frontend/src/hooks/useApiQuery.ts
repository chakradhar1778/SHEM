import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CONNECTION_CHANGED_EVENT, DATA_CHANGED_EVENT, errorMessage } from '../api/backendApi';

export interface ApiQuery<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

interface Settled<T> {
  requestId: string;
  data: T | null;
  error: string | null;
}

/**
 * Fetch backend data for a page. Re-runs when `key` changes, when the backend
 * connection settings change, and every `refreshIntervalMs` if given.
 * Keeps the last good data while a refresh is in flight.
 */
export function useApiQuery<T>(fetcher: () => Promise<T>, key: string, refreshIntervalMs?: number): ApiQuery<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({ requestId: '', data: null, error: null });
  const fetcherRef = useRef(fetcher);
  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
  });

  const requestId = `${key}#${nonce}`;

  useEffect(() => {
    let cancelled = false;
    fetcherRef.current()
      .then((data) => {
        if (!cancelled) setSettled({ requestId, data, error: null });
      })
      .catch((err) => {
        if (!cancelled) setSettled((prev) => ({ requestId, data: prev.data, error: errorMessage(err) }));
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  useEffect(() => {
    const bump = () => setNonce((n) => n + 1);
    window.addEventListener(CONNECTION_CHANGED_EVENT, bump);
    window.addEventListener(DATA_CHANGED_EVENT, bump);
    const timer = refreshIntervalMs ? setInterval(bump, refreshIntervalMs) : null;
    return () => {
      window.removeEventListener(CONNECTION_CHANGED_EVENT, bump);
      window.removeEventListener(DATA_CHANGED_EVENT, bump);
      if (timer) clearInterval(timer);
    };
  }, [refreshIntervalMs]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return {
    data: settled.data,
    loading: settled.requestId !== requestId,
    error: settled.requestId === requestId ? settled.error : null,
    refresh,
  };
}
