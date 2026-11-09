import { apiRequest } from './backendApi';
import type { ApplianceDTO, RoomDTO } from './types';

export const fetchRooms = () => apiRequest<RoomDTO[]>('/api/inventory/rooms');

export const createRoom = (room: { id?: string; name: string; roomType?: string; floor?: number }) =>
  apiRequest<RoomDTO>('/api/inventory/rooms', { method: 'POST', body: room });

export const updateRoom = (id: string, patch: { name?: string; roomType?: string; floor?: number }) =>
  apiRequest<RoomDTO>(`/api/inventory/rooms/${encodeURIComponent(id)}`, { method: 'PUT', body: patch });

export const deleteRoom = (id: string) =>
  apiRequest<void>(`/api/inventory/rooms/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const fetchAppliances = () => apiRequest<ApplianceDTO[]>('/api/inventory/appliances');

export type ApplianceWrite = Partial<Omit<ApplianceDTO, 'createdAt' | 'updatedAt'>>;

export const createAppliance = (appliance: ApplianceWrite & { name: string }) =>
  apiRequest<ApplianceDTO>('/api/inventory/appliances', { method: 'POST', body: appliance });

export const updateAppliance = (id: string, patch: ApplianceWrite) =>
  apiRequest<ApplianceDTO>(`/api/inventory/appliances/${encodeURIComponent(id)}`, { method: 'PUT', body: patch });

export const deleteAppliance = (id: string) =>
  apiRequest<void>(`/api/inventory/appliances/${encodeURIComponent(id)}`, { method: 'DELETE' });
