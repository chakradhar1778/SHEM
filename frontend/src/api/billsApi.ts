import { apiBlob, apiRequest, apiUpload } from './backendApi';
import type { BillDTO } from './types';

export type BillWrite = Partial<Omit<BillDTO, 'createdAt' | 'hasDocument' | 'documentContentType' | 'documentSize' | 'documentUploadedAt'>>;

export const fetchBills = () => apiRequest<BillDTO[]>('/api/bills');

export const createBill = (bill: BillWrite & { unitsConsumedKWh: number; billAmountINR: number }) =>
  apiRequest<BillDTO>('/api/bills', { method: 'POST', body: bill });

export const updateBill = (id: string, patch: BillWrite) =>
  apiRequest<BillDTO>(`/api/bills/${encodeURIComponent(id)}`, { method: 'PUT', body: patch });

export const deleteBill = (id: string) =>
  apiRequest<void>(`/api/bills/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Allowed bill documents (verified again on the server from the file bytes). */
export const BILL_DOCUMENT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
export const BILL_DOCUMENT_MAX_MB = 10;

export const uploadBillDocument = (id: string, file: File) =>
  apiUpload<BillDTO>(`/api/bills/${encodeURIComponent(id)}/document?filename=${encodeURIComponent(file.name.slice(0, 200))}`, file);

export const fetchBillDocument = (id: string) => apiBlob(`/api/bills/${encodeURIComponent(id)}/document`);

export const deleteBillDocument = (id: string) =>
  apiRequest<BillDTO>(`/api/bills/${encodeURIComponent(id)}/document`, { method: 'DELETE' });
