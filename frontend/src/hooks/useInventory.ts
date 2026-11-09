import { useContext } from 'react';
import { InventoryContext } from '../context/inventoryContextDef';
import type { InventoryContextType } from '../context/inventoryContextDef';

export function useInventory(): InventoryContextType {
  const ctx = useContext(InventoryContext);
  if (!ctx) {
    throw new Error('useInventory must be used within an InventoryProvider');
  }
  return ctx;
}
