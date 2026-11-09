import { apiRequest } from './backendApi';
import type { RelayState, SimStatus } from './types';

export const fetchSimStatus = () => apiRequest<SimStatus>('/api/simulation/status');

/** Switch a simulated appliance. Applies immediately (no device acknowledgement). */
export const sendSimCommand = (applianceId: string, state: RelayState) =>
  apiRequest<SimStatus>(`/api/simulation/appliances/${encodeURIComponent(applianceId)}/command`, {
    method: 'POST',
    body: { state },
  });

/** Drop the manual override so the appliance follows its daily routine again. */
export const resumeSimRoutine = (applianceId: string) =>
  apiRequest<SimStatus>(`/api/simulation/appliances/${encodeURIComponent(applianceId)}/auto`, { method: 'POST' });
