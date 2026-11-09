import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { errorMessage } from '../api/backendApi';
import { fetchHouseholdConfig, updateHouseholdConfig } from '../api/householdApi';
import type { HouseholdConfigDTO } from '../api/types';
import { HomeContext, DEFAULT_HOME_CONFIG } from './homeContextDef';
import type { HomeConfig } from './homeContextDef';
import { useLoadOnConnection } from './syncState';

function fromDTO(dto: HouseholdConfigDTO): HomeConfig {
  return {
    homeName: dto.homeName,
    homeType: dto.homeType,
    occupants: dto.occupants,
    location: dto.location ?? '',
    tariffRateINR: dto.tariffRateINRPerKWh,
    isConfigured: dto.isConfigured,
  };
}

function toDTO(config: Partial<HomeConfig>): Partial<HouseholdConfigDTO> {
  const out: Partial<HouseholdConfigDTO> = {};
  if (config.homeName !== undefined) out.homeName = config.homeName.trim() || 'My Home';
  if (config.homeType !== undefined) out.homeType = config.homeType || 'Apartment';
  if (config.occupants !== undefined) out.occupants = config.occupants;
  if (config.location !== undefined) out.location = config.location.trim() || null;
  if (config.tariffRateINR !== undefined) out.tariffRateINRPerKWh = config.tariffRateINR;
  if (config.isConfigured !== undefined) out.isConfigured = config.isConfigured;
  return out;
}

/** Household configuration, persisted in the backend (household_config table). */
export function HomeProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<HomeConfig>(DEFAULT_HOME_CONFIG);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const configRef = useRef(config);
  useLayoutEffect(() => {
    configRef.current = config;
  }, [config]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setConfig(fromDTO(await fetchHouseholdConfig()));
      setLoaded(true);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useLoadOnConnection(refresh);

  const persist = useCallback(
    (patch: Partial<HomeConfig>) => {
      setConfig((prev) => ({ ...prev, ...patch }));          // optimistic
      updateHouseholdConfig(toDTO(patch))
        .then((dto) => {
          setConfig(fromDTO(dto));
          setError(null);
        })
        .catch((e) => {
          // reload server state first, then report (refresh clears errors on success)
          void refresh().then(() => setError(`Could not save home setup: ${errorMessage(e)}`));
        });
    },
    [refresh]
  );

  const saveConfig = useCallback((newConfig: HomeConfig) => persist(newConfig), [persist]);
  const updateConfig = useCallback((partial: Partial<HomeConfig>) => persist(partial), [persist]);
  const resetConfig = useCallback(
    () => persist({ ...DEFAULT_HOME_CONFIG, tariffRateINR: configRef.current.tariffRateINR }),
    [persist]
  );

  return (
    <HomeContext.Provider value={{ config, updateConfig, saveConfig, resetConfig, loading, loaded, error, refresh }}>
      {children}
    </HomeContext.Provider>
  );
}
