import { apiRequest } from './backendApi';
import type { BillApplianceBreakdown, BillBreakdown, BillProjection, Tariff } from './types';

export const fetchTariff = () => apiRequest<Tariff>('/api/billing/tariff');

export type TariffWrite = Partial<Omit<Tariff, 'utilityProvider'>>;

export const updateTariff = (patch: TariffWrite) =>
  apiRequest<Tariff>('/api/billing/tariff', { method: 'PUT', body: patch });

/** Current billing cycle: usage and bill so far, projected bill, budget status. */
export const fetchBillProjection = () => apiRequest<BillProjection>('/api/billing/projection');

/** Itemised bill for `kwh` units in one cycle under the saved tariff. */
export const estimateBill = (kwh: number) =>
  apiRequest<BillBreakdown>('/api/billing/estimate', { method: 'POST', body: { kwh } });

/** Split a recorded bill across appliances (metered + simulated kWh in the bill's period). */
export const fetchBillAppliances = (billId: string) =>
  apiRequest<BillApplianceBreakdown>(`/api/billing/bills/${encodeURIComponent(billId)}/appliances`);
