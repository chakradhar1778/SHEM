import { useContext } from 'react';
import { BillContext } from '../context/billContextDef';
import type { BillContextType } from '../context/billContextDef';

/**
 * Custom React hook to access electricity bill state and methods.
 * Must be used within a <BillProvider>.
 */
export function useBill(): BillContextType {
  const ctx = useContext(BillContext);
  if (!ctx) {
    throw new Error('useBill must be used within a BillProvider');
  }
  return ctx;
}
