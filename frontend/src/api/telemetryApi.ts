import { apiRequest } from './backendApi';
import type { DeviceStatus, HealthResponse, LatestTelemetryResponse, TelemetryHistoryResponse } from './types';

export type HistoryResolution = 'auto' | 'raw' | '1m' | '5m' | '15m' | '1h';

export const fetchHealth = () => apiRequest<HealthResponse>('/api/health');

export const fetchDeviceStatus = () => apiRequest<DeviceStatus>('/api/device/status');

export const fetchLatestTelemetry = () => apiRequest<LatestTelemetryResponse>('/api/telemetry/latest');

export function fetchTelemetryHistory(params: {
  from?: Date;
  to?: Date;
  resolution?: HistoryResolution;
  limit?: number;
}): Promise<TelemetryHistoryResponse> {
  const q = new URLSearchParams();
  if (params.from) q.set('from_time', params.from.toISOString());
  if (params.to) q.set('to_time', params.to.toISOString());
  if (params.resolution) q.set('resolution', params.resolution);
  if (params.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  return apiRequest<TelemetryHistoryResponse>(`/api/telemetry/history${qs ? `?${qs}` : ''}`);
}
