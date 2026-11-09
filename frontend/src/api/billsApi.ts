import { apiRequest } from './backendApi';
import type { BillDTO } from './types';

export type BillWrite = Partial<Omit<BillDTO, 'createdAt'>>;

export const fetchBills = () => apiRequest<BillDTO[]>('/api/bills');

export const createBill = (bill: BillWrite & { unitsConsumedKWh: number; billAmountINR: number }) =>
  apiRequest<BillDTO>('/api/bills', { method: 'POST', body: bill });

export const updateBill = (id: string, patch: BillWrite) =>
  apiRequest<BillDTO>(`/api/bills/${encodeURIComponent(id)}`, { method: 'PUT', body: patch });

export const deleteBill = (id: string) =>
  apiRequest<void>(`/api/bills/${encodeURIComponent(id)}`, { method: 'DELETE' });
