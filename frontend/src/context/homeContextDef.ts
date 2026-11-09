import { createContext } from 'react';
import type { SyncState } from './syncState';

export interface HomeConfig {
  homeName: string;
  homeType: string;
  occupants: number;
  location: string;
  /** Electricity tariff used for cost estimates (₹/kWh), stored on the backend. */
  tariffRateINR: number;
  isConfigured: boolean;
}

/** Form defaults only — the real configuration always comes from the backend. */
export const DEFAULT_HOME_CONFIG: HomeConfig = {
  homeName: 'My Home',
  homeType: 'Apartment',
  occupants: 2,
  location: '',
  tariffRateINR: 7.5,
  isConfigured: false,
};

export interface HomeContextType extends SyncState {
  config: HomeConfig;
  updateConfig: (partial: Partial<HomeConfig>) => void;
  saveConfig: (newConfig: HomeConfig) => void;
  resetConfig: () => void;
}

export const HomeContext = createContext<HomeContextType | null>(null);
