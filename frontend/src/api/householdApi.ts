import { apiRequest } from './backendApi';
import type { HouseholdConfigDTO } from './types';

export const fetchHouseholdConfig = () => apiRequest<HouseholdConfigDTO>('/api/household/config');

export const updateHouseholdConfig = (patch: Partial<Omit<HouseholdConfigDTO, 'updatedAt'>>) =>
  apiRequest<HouseholdConfigDTO>('/api/household/config', { method: 'PUT', body: patch });
