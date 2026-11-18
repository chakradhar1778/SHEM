import { apiRequest } from './backendApi';
import type {
  ApplianceDTO,
  RelayCommandDetail,
  RelayCommandResponse,
  RelayMismatchConfirmSameResponse,
  RelayMismatchStatus,
  RelayState,
  RelayStatus,
} from './types';

export const fetchRelayStatus = () => apiRequest<RelayStatus>('/api/relay/1/status');

/** Returns once the command is PUBLISHED — not applied. Wait for the ack. */
export const sendRelayCommand = (state: RelayState) =>
  apiRequest<RelayCommandResponse>('/api/relay/1/command', { method: 'POST', body: { state } });

export const fetchRelayCommand = (commandId: string) =>
  apiRequest<RelayCommandDetail>(`/api/relay/1/commands/${encodeURIComponent(commandId)}`);

export const fetchRelayMismatch = () => apiRequest<RelayMismatchStatus>('/api/relay/1/mismatch');

export const confirmRelaySameAppliance = () =>
  apiRequest<RelayMismatchConfirmSameResponse>('/api/relay/1/mismatch/confirm-same', { method: 'POST' });

export const switchRelayAppliance = (applianceId: string) =>
  apiRequest<ApplianceDTO>('/api/relay/1/mismatch/switch', { method: 'POST', body: { applianceId } });
