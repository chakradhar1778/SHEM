import { createContext } from 'react';
import type { SyncState } from './syncState';

/**
 * Configuration (stored in the backend energy_targets table) for the user's monthly electricity budget target.
 */
export interface TargetConfig {
  /** User-configured monthly budget in Indian Rupees (INR) */
  monthlyBudgetINR: number;

  /** Whether the user has explicitly configured and saved a target */
  isConfigured: boolean;

  /** Target type: 'budget' (monthly rupee target) or 'reduction' (percentage/usage goal) */
  targetType: 'budget' | 'reduction';

  /** Timestamp when the target was first created */
  createdAt?: number;

  /** Timestamp when the target was last updated */
  updatedAt?: number;
}

/**
 * Bounds and defaults for energy target validation.
 */
export const TARGET_CONSTRAINTS = {
  MIN_AMOUNT_INR: 100,
  MAX_AMOUNT_INR: 50000,
  SLIDER_MIN_INR: 1000,
  SLIDER_MAX_INR: 3000,
  SLIDER_STEP_INR: 50,
  DEFAULT_SUGGESTED_INR: 1800,
} as const;

/**
 * Context interface for the Energy Target module.
 */
export interface TargetContextType extends SyncState {
  /** Active target configuration */
  target: TargetConfig;

  /** Validates and saves a new monthly budget in INR */
  saveTarget: (amountINR: number, type?: 'budget' | 'reduction') => boolean;

  /** Clears the configured target, returning to unconfigured state */
  clearTarget: () => void;

  /** Validates an input amount against target constraints */
  validateAmount: (amountINR: number) => { valid: boolean; error?: string };
}

export const TargetContext = createContext<TargetContextType | null>(null);
