import { createContext } from 'react';
import type { CatalogueItem } from '../data/applianceCatalogue';
import type { SyncState } from './syncState';

export interface Room {
  id: string;
  name: string;
  icon?: string;
  isCustom?: boolean;
}

export type EssentialStatus = 'yes' | 'no' | 'unsure';

export interface InventoryItem {
  id: string;
  catalogueId: string;
  name: string;
  brand?: string;
  model?: string;
  isEssential?: EssentialStatus;
  category: string;
  iconType: string;
  /** '' when the appliance is not assigned to a room */
  roomId: string;
  quantity: number;
  ratedWatts: number;
  /** True when the rated wattage is the catalogue's typical example value */
  isExample: boolean;
  addedAt: number;
  dailyHours?: number;
  /** Relay channel switching this appliance; null/undefined = not relay-controlled */
  relayChannel?: number | null;
  /** Simulated appliances (no relay): follow the daily routine from dailyHours */
  simAuto?: boolean;
}

export interface InventoryContextType extends SyncState {
  rooms: Room[];
  inventory: InventoryItem[];
  addAppliance: (
    catalogueItem: CatalogueItem,
    roomId: string,
    quantity: number,
    metadata?: { brand?: string; model?: string; isEssential?: EssentialStatus; relayChannel?: number | null; dailyHours?: number; simAuto?: boolean }
  ) => void;
  updateQuantity: (itemId: string, delta: number) => void;
  setQuantity: (itemId: string, quantity: number) => void;
  updateRoom: (itemId: string, newRoomId: string) => void;
  removeAppliance: (itemId: string) => void;
  addCustomRoom: (roomName: string) => Room | null;
  updateDailyHours: (itemId: string, hours: number) => void;
  updateApplianceDetails: (
    itemId: string,
    updates: {
      brand?: string;
      model?: string;
      isEssential?: EssentialStatus;
      ratedWatts?: number;
      quantity?: number;
      roomId?: string;
      dailyHours?: number;
      /** number = assign, null = detach, undefined = leave unchanged */
      relayChannel?: number | null;
      simAuto?: boolean;
    }
  ) => void;
  totalEntries: number;
  totalQuantity: number;
  totalConfiguredRatedWatts: number;
}

export const InventoryContext = createContext<InventoryContextType | null>(null);
