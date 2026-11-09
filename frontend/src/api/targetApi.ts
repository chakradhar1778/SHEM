import { apiRequest } from './backendApi';
import type { TargetDTO } from './types';

export const fetchTarget = () => apiRequest<TargetDTO>('/api/target');

export const saveTarget = (monthlyBudgetINR: number, targetType: 'budget' | 'reduction') =>
  apiRequest<TargetDTO>('/api/target', { method: 'PUT', body: { monthlyBudgetINR, targetType } });

export const clearTarget = () => apiRequest<void>('/api/target', { method: 'DELETE' });
