import { useState, useCallback, type ReactNode } from 'react';
import { errorMessage } from '../api/backendApi';
import { clearTarget as apiClearTarget, fetchTarget, saveTarget as apiSaveTarget } from '../api/targetApi';
import type { TargetDTO } from '../api/types';
import {
  TargetContext,
  TARGET_CONSTRAINTS,
  type TargetConfig,
  type TargetContextType,
} from './targetContextDef';
import { useLoadOnConnection } from './syncState';

const DEFAULT_UNCONFIGURED_TARGET: TargetConfig = {
  monthlyBudgetINR: 0,
  isConfigured: false,
  targetType: 'budget',
};

function fromDTO(dto: TargetDTO): TargetConfig {
  if (!dto.isConfigured) return DEFAULT_UNCONFIGURED_TARGET;
  return {
    monthlyBudgetINR: Math.round(dto.monthlyBudgetINR),
    isConfigured: true,
    targetType: dto.targetType,
    updatedAt: dto.updatedAt ? Date.parse(dto.updatedAt) : undefined,
  };
}

/** Monthly energy target, persisted in the backend (energy_targets table). */
export function TargetProvider({ children }: { children: ReactNode }) {
  const [target, setTargetState] = useState<TargetConfig>(DEFAULT_UNCONFIGURED_TARGET);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTargetState(fromDTO(await fetchTarget()));
      setLoaded(true);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useLoadOnConnection(refresh);

  const validateAmount = useCallback((amountINR: number): { valid: boolean; error?: string } => {
    const num = Number(amountINR);
    if (!Number.isFinite(num)) {
      return { valid: false, error: 'Please enter a valid numeric amount in Rupees.' };
    }
    if (num < TARGET_CONSTRAINTS.MIN_AMOUNT_INR) {
      return {
        valid: false,
        error: `Target amount must be at least ₹${TARGET_CONSTRAINTS.MIN_AMOUNT_INR.toLocaleString('en-IN')}.`,
      };
    }
    if (num > TARGET_CONSTRAINTS.MAX_AMOUNT_INR) {
      return {
        valid: false,
        error: `Target amount cannot exceed ₹${TARGET_CONSTRAINTS.MAX_AMOUNT_INR.toLocaleString('en-IN')}.`,
      };
    }
    return { valid: true };
  }, []);

  const saveTarget = useCallback(
    (amountINR: number, type: 'budget' | 'reduction' = 'budget'): boolean => {
      if (!validateAmount(amountINR).valid) return false;
      const rounded = Math.round(Number(amountINR));
      setTargetState((prev) => ({ ...prev, monthlyBudgetINR: rounded, isConfigured: true, targetType: type, updatedAt: Date.now() }));
      apiSaveTarget(rounded, type)
        .then((dto) => {
          setTargetState(fromDTO(dto));
          setError(null);
        })
        .catch((e) => {
          // reload server state first, then report (refresh clears errors on success)
          void refresh().then(() => setError(`Could not save target: ${errorMessage(e)}`));
        });
      return true;
    },
    [validateAmount, refresh]
  );

  const clearTarget = useCallback(() => {
    setTargetState(DEFAULT_UNCONFIGURED_TARGET);
    apiClearTarget().catch((e) => {
      // reload server state first, then report (refresh clears errors on success)
      void refresh().then(() => setError(`Could not clear target: ${errorMessage(e)}`));
    });
  }, [refresh]);

  const contextValue: TargetContextType = {
    target,
    saveTarget,
    clearTarget,
    validateAmount,
    loading,
    loaded,
    error,
    refresh,
  };

  return <TargetContext.Provider value={contextValue}>{children}</TargetContext.Provider>;
}
