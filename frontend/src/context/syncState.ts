import { useEffect } from 'react';
import { CONNECTION_CHANGED_EVENT, DATA_CHANGED_EVENT } from '../api/backendApi';

/** Common backend-sync status exposed by every data context. */
export interface SyncState {
  /** A request to load data from the backend is in flight. */
  loading: boolean;
  /** Data has been loaded from the backend at least once. */
  loaded: boolean;
  /** Last load/save error (null when the last operation succeeded). */
  error: string | null;
  /** Reload everything from the backend (discarding optimistic state). */
  refresh: () => Promise<void>;
}

/** Run `load` now, whenever backend connection settings change, and when data changed elsewhere (SHEM AI). */
export function useLoadOnConnection(load: () => Promise<void>): void {
  useEffect(() => {
    void load();
    const onChange = () => void load();
    window.addEventListener(CONNECTION_CHANGED_EVENT, onChange);
    window.addEventListener(DATA_CHANGED_EVENT, onChange);
    return () => {
      window.removeEventListener(CONNECTION_CHANGED_EVENT, onChange);
      window.removeEventListener(DATA_CHANGED_EVENT, onChange);
    };
  }, [load]);
}
