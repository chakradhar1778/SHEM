import { apiRequest } from './backendApi';
import type { RelayCommandDetail, RelayCommandResponse, RelayState, RelayStatus } from './types';

export const fetchRelayStatus = () => apiRequest<RelayStatus>('/api/relay/1/status');

/** Returns once the command is PUBLISHED — not applied. Wait for the ack. */
export const sendRelayCommand = (state: RelayState) =>
  apiRequest<RelayCommandResponse>('/api/relay/1/command', { method: 'POST', body: { state } });

export const fetchRelayCommand = (commandId: string) =>
  apiRequest<RelayCommandDetail>(`/api/relay/1/commands/${encodeURIComponent(commandId)}`);
