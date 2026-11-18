import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CONNECTION_CHANGED_EVENT,
  DATA_CHANGED_EVENT,
  NOTIFICATION_EVENT,
} from '../api/backendApi';
import { fetchRelayMismatch } from '../api/relayApi';
import type { RelayMismatchStatus } from '../api/types';
import { useHomeConfig } from './useHomeConfig';
import { useInventory } from './useInventory';
import { useLiveData } from './useLiveData';

export const OPEN_RELAY_MISMATCH_EVENT = 'shem:open-relay-mismatch';
export const RELAY_MISMATCH_CHANGED_EVENT = 'shem:relay-mismatch-changed';

export function openRelayMismatchModal(): void {
  window.dispatchEvent(new CustomEvent(OPEN_RELAY_MISMATCH_EVENT));
}

export function notifyRelayMismatchChanged(): void {
  window.dispatchEvent(new CustomEvent(RELAY_MISMATCH_CHANGED_EVENT));
}

/**
 * Tracks live Relay 1 load mismatch status from the backend.
 * Refreshes automatically on inventory/relay/threshold/notification changes
 * and throttled live power updates.
 */
export function useRelayMismatch() {
  const { latest, relay } = useLiveData();
  const { inventory } = useInventory();
  const { config } = useHomeConfig();
  const [mismatch, setMismatch] = useState<RelayMismatchStatus | null>(null);
  const lastFetchRef = useRef(0);

  const relayOwner = inventory.find((i) => i.relayChannel === 1);
  const relayOwnerKey = relayOwner ? `${relayOwner.id}:${relayOwner.ratedWatts}` : 'none';

  const refresh = useCallback(async () => {
    lastFetchRef.current = Date.now();
    try {
      const status = await fetchRelayMismatch();
      setMismatch(status);
    } catch {
      /* backend unreachable — keep last known state */
    }
  }, []);

  // Immediate refresh when relay owner, relay commanded state, or threshold changes
  useEffect(() => {
    let cancelled = false;
    lastFetchRef.current = Date.now();
    fetchRelayMismatch()
      .then((status) => {
        if (!cancelled) setMismatch(status);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [relayOwnerKey, relay?.commandedState, config.relayMismatchThresholdPercent]);

  // Throttled refresh when live wattage changes while relay is ON
  const livePower = latest?.activePowerW ?? null;
  useEffect(() => {
    if (relay?.commandedState !== 'ON' || livePower == null) return;
    const elapsed = Date.now() - lastFetchRef.current;
    if (elapsed >= 3500) {
      void refresh();
      return;
    }
    const timer = window.setTimeout(() => void refresh(), 3500 - elapsed);
    return () => window.clearTimeout(timer);
  }, [livePower, relay?.commandedState, refresh]);

  // Refresh on relevant global events
  useEffect(() => {
    const onRefresh = () => void refresh();
    window.addEventListener(CONNECTION_CHANGED_EVENT, onRefresh);
    window.addEventListener(DATA_CHANGED_EVENT, onRefresh);
    window.addEventListener(NOTIFICATION_EVENT, onRefresh);
    window.addEventListener(RELAY_MISMATCH_CHANGED_EVENT, onRefresh);
    return () => {
      window.removeEventListener(CONNECTION_CHANGED_EVENT, onRefresh);
      window.removeEventListener(DATA_CHANGED_EVENT, onRefresh);
      window.removeEventListener(NOTIFICATION_EVENT, onRefresh);
      window.removeEventListener(RELAY_MISMATCH_CHANGED_EVENT, onRefresh);
    };
  }, [refresh]);

  return { mismatch, refresh };
}
