import React, { useState, useMemo, useCallback, useLayoutEffect, useRef } from 'react';
import { errorMessage, newId } from '../api/backendApi';
import {
  createBill,
  deleteBill as apiDeleteBill,
  deleteBillDocument,
  fetchBills,
  updateBill as apiUpdateBill,
  uploadBillDocument,
  type BillWrite,
} from '../api/billsApi';
import type { BillDTO } from '../api/types';
import {
  BillContext,
  isHomeBill,
  type BillRecord,
  type BillInput,
} from './billContextDef';
import { validateBillData } from '../utils/billMath';
import { useLoadOnConnection } from './syncState';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function getPeriodLabel(month: number, year: number): string {
  const mName = MONTH_NAMES[month - 1] ?? `Month ${month}`;
  return `${mName} ${year}`;
}

function sortBills(bills: BillRecord[]): BillRecord[] {
  return [...bills].sort((a, b) => {
    if (a.billingYear !== b.billingYear) return b.billingYear - a.billingYear;
    if (a.billingMonth !== b.billingMonth) return b.billingMonth - a.billingMonth;
    return b.createdAt - a.createdAt;
  });
}

function fromDTO(dto: BillDTO): BillRecord {
  const now = new Date();
  const month = dto.billingMonth ?? now.getMonth() + 1;
  const year = dto.billingYear ?? now.getFullYear();
  return {
    id: dto.id,
    utilityProvider: dto.utilityProvider || 'BESCOM',
    accountId: dto.accountId ?? undefined,
    billingMonth: month,
    billingYear: year,
    billingPeriod: dto.billingPeriod || getPeriodLabel(month, year),
    billingPeriodStart: dto.billingPeriodStart ?? undefined,
    billingPeriodEnd: dto.billingPeriodEnd ?? undefined,
    billingPeriodDays: dto.billingPeriodDays ?? new Date(year, month, 0).getDate(),
    unitsConsumed: dto.unitsConsumedKWh,
    billAmount: dto.billAmountINR,
    dueDate: dto.dueDate ?? undefined,
    locationTag: dto.locationTag || 'my_home',
    documentFilename: dto.documentFilename ?? undefined,
    hasDocument: dto.hasDocument ?? false,
    documentContentType: dto.documentContentType ?? undefined,
    documentSize: dto.documentSize ?? undefined,
    createdAt: dto.createdAt ? Date.parse(dto.createdAt) : Date.now(),
  };
}

function toWrite(record: BillRecord): BillWrite & { unitsConsumedKWh: number; billAmountINR: number } {
  return {
    id: record.id,
    utilityProvider: record.utilityProvider,
    accountId: record.accountId ?? null,
    billingMonth: record.billingMonth,
    billingYear: record.billingYear,
    billingPeriod: record.billingPeriod ?? null,
    billingPeriodStart: record.billingPeriodStart ?? null,
    billingPeriodEnd: record.billingPeriodEnd ?? null,
    billingPeriodDays: record.billingPeriodDays ?? null,
    dueDate: record.dueDate ?? null,
    documentFilename: record.documentFilename ?? null,
    unitsConsumedKWh: record.unitsConsumed,
    billAmountINR: record.billAmount,
    locationTag: record.locationTag ?? 'my_home',
  };
}

/** Electricity bills, persisted in the backend (electricity_bills table). */
export function BillProvider({ children }: { children: React.ReactNode }) {
  const [bills, setBills] = useState<BillRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<string>('my_home');
  const billsRef = useRef(bills);
  useLayoutEffect(() => {
    billsRef.current = bills;
  }, [bills]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setBills(sortBills((await fetchBills()).map(fromDTO)));
      setLoaded(true);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useLoadOnConnection(refresh);

  const syncFailed = useCallback(
    (action: string) => (e: unknown) => {
      // reload server state first, then report (refresh clears errors on success)
      void refresh().then(() => setError(`Could not ${action}: ${errorMessage(e)}`));
    },
    [refresh]
  );

  // Bills for other locations (parents' home, office) are kept but never compared with this home.
  const homeBills = useMemo(() => bills.filter(isHomeBill), [bills]);
  const latestBill = useMemo<BillRecord | null>(() => (homeBills.length > 0 ? homeBills[0] : null), [homeBills]);

  // Bill creations in flight: a document upload for that bill waits for it.
  const pendingCreates = useRef<Map<string, Promise<unknown>>>(new Map());

  const patchBill = (id: string, patch: Partial<BillRecord>) =>
    setBills((prev) => prev.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  const attachDocument = async (id: string, file: File): Promise<string | null> => {
    patchBill(id, { documentStatus: 'uploading' });
    try {
      await pendingCreates.current.get(id);
      const dto = await uploadBillDocument(id, file);
      setBills((prev) => sortBills(prev.map((b) => (b.id === dto.id ? fromDTO(dto) : b))));
      return null;
    } catch (e) {
      patchBill(id, { documentStatus: 'failed' });
      return errorMessage(e);
    }
  };

  const removeDocument = async (id: string): Promise<string | null> => {
    try {
      const dto = await deleteBillDocument(id);
      setBills((prev) => sortBills(prev.map((b) => (b.id === dto.id ? fromDTO(dto) : b))));
      return null;
    } catch (e) {
      return errorMessage(e);
    }
  };

  const addBill = (input: BillInput, file?: File | null): BillRecord | null => {
    const validation = validateBillData(input);
    if (!validation.isValid) {
      console.warn('Invalid bill input data:', validation.errors);
      return null;
    }

    const now = new Date();
    const month = input.billingMonth ? Math.max(1, Math.min(12, Number(input.billingMonth))) : now.getMonth() + 1;
    const year = input.billingYear ? Number(input.billingYear) : now.getFullYear();

    const record: BillRecord = {
      id: newId('bill'),
      utilityProvider: input.utilityProvider?.trim() || 'BESCOM',
      accountId: input.accountId?.trim() || undefined,
      billingMonth: month,
      billingYear: year,
      billingPeriod: input.billingPeriod?.trim() || getPeriodLabel(month, year),
      billingPeriodStart: input.billingPeriodStart || undefined,
      billingPeriodEnd: input.billingPeriodEnd || undefined,
      billingPeriodDays: input.billingPeriodDays && input.billingPeriodDays > 0
        ? input.billingPeriodDays
        : new Date(year, month, 0).getDate(),
      unitsConsumed: Number(input.unitsConsumed),
      billAmount: Number(input.billAmount),
      dueDate: input.dueDate || undefined,
      locationTag: input.locationTag?.trim() || 'my_home',
      documentFilename: input.documentFilename,
      createdAt: Date.now(),
    };

    setBills((prev) => sortBills([record, ...prev]));
    const created = createBill(toWrite(record))
      .then((dto) => {
        setBills((prev) => sortBills(prev.map((b) => (b.id === dto.id ? fromDTO(dto) : b))));
        setError(null);
      });
    pendingCreates.current.set(record.id, created.catch(() => undefined));
    created
      .catch(syncFailed('save the bill'))
      .finally(() => pendingCreates.current.delete(record.id));
    if (file) {
      void created.then(() => attachDocument(record.id, file)).then((err) => {
        if (err) setError(`The bill was saved, but its document could not be stored: ${err}`);
      }).catch(() => undefined);
    }
    return record;
  };

  const updateBill = (id: string, input: Partial<BillInput>): BillRecord | null => {
    const existing = billsRef.current.find((b) => b.id === id);
    if (!existing) {
      console.warn(`Cannot update bill: record with id ${id} not found.`);
      return null;
    }
    const validation = validateBillData({ ...existing, ...input });
    if (!validation.isValid) {
      console.warn('Invalid bill update data:', validation.errors);
      return null;
    }

    const month = input.billingMonth !== undefined ? Number(input.billingMonth) : existing.billingMonth;
    const year = input.billingYear !== undefined ? Number(input.billingYear) : existing.billingYear;
    const periodLabel = input.billingPeriod?.trim()
      || (input.billingMonth !== undefined || input.billingYear !== undefined
        ? getPeriodLabel(month, year)
        : existing.billingPeriod);

    const updated: BillRecord = {
      ...existing,
      ...input,
      utilityProvider: input.utilityProvider !== undefined ? input.utilityProvider.trim() : existing.utilityProvider,
      billingMonth: month,
      billingYear: year,
      billingPeriod: periodLabel,
      unitsConsumed: input.unitsConsumed !== undefined ? Number(input.unitsConsumed) : existing.unitsConsumed,
      billAmount: input.billAmount !== undefined ? Number(input.billAmount) : existing.billAmount,
    };

    setBills((prev) => sortBills(prev.map((b) => (b.id === id ? updated : b))));
    const { id: _omit, ...patch } = toWrite(updated);
    void _omit;
    apiUpdateBill(id, patch)
      .then((dto) => {
        setBills((prev) => sortBills(prev.map((b) => (b.id === dto.id ? fromDTO(dto) : b))));
        setError(null);
      })
      .catch(syncFailed('update the bill'));
    return updated;
  };

  const deleteBill = (id: string): boolean => {
    if (!billsRef.current.some((b) => b.id === id)) return false;
    setBills((prev) => prev.filter((b) => b.id !== id));
    apiDeleteBill(id).catch(syncFailed('delete the bill'));
    return true;
  };

  return (
    <BillContext.Provider
      value={{
        bills,
        homeBills,
        latestBill,
        addBill,
        attachDocument,
        removeDocument,
        updateBill,
        deleteBill,
        selectedLocation,
        setSelectedLocation,
        loading,
        loaded,
        error,
        refresh,
      }}
    >
      {children}
    </BillContext.Provider>
  );
}
