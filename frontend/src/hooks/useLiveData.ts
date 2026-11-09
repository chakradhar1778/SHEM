import { useContext } from 'react';
import { LiveDataContext, type LiveDataContextType } from '../context/liveDataContextDef';

/** Live AC telemetry, device/MQTT status and relay control from the backend stream. */
export function useLiveData(): LiveDataContextType {
  const ctx = useContext(LiveDataContext);
  if (!ctx) throw new Error('useLiveData must be used within a LiveDataProvider');
  return ctx;
}
