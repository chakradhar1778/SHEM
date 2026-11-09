import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { errorMessage, newId } from '../api/backendApi';
import {
  createAppliance,
  createRoom,
  deleteAppliance,
  fetchAppliances,
  fetchRooms,
  updateAppliance,
  type ApplianceWrite,
} from '../api/inventoryApi';
import type { ApplianceDTO, RoomDTO } from '../api/types';
import { APPLIANCE_CATEGORIES, type CatalogueItem } from '../data/applianceCatalogue';
import { getDefaultDailyHours } from '../utils/energyMath';
import { InventoryContext } from './inventoryContextDef';
import type { EssentialStatus, InventoryItem, Room } from './inventoryContextDef';
import { useLoadOnConnection } from './syncState';

const ROOM_ICONS: Record<string, string> = {
  living: '🛋️',
  kitchen: '🍳',
  bedroom: '🛏️',
  bathroom: '🚿',
  balcony: '🌿',
};

const CATALOGUE = new Map(APPLIANCE_CATEGORIES.flatMap((c) => c.items).map((i) => [i.id, i]));

function roomFromDTO(dto: RoomDTO): Room {
  const type = dto.roomType ?? 'custom';
  return { id: dto.id, name: dto.name, icon: ROOM_ICONS[type] ?? '🏠', isCustom: !(type in ROOM_ICONS) };
}

function itemFromDTO(dto: ApplianceDTO): InventoryItem {
  const catalogue = dto.catalogueId ? CATALOGUE.get(dto.catalogueId) : undefined;
  const ratedWatts = dto.ratedWatts ?? 0;
  return {
    id: dto.id,
    catalogueId: dto.catalogueId ?? '',
    name: dto.name,
    brand: dto.brand ?? undefined,
    model: dto.model ?? undefined,
    isEssential: dto.isEssential ?? undefined,
    category: dto.category ?? 'Other',
    iconType: dto.iconType ?? catalogue?.iconType ?? 'bulb',
    roomId: dto.roomId ?? '',
    quantity: dto.quantity,
    ratedWatts,
    isExample: !!catalogue && catalogue.isExample && catalogue.ratedWatts === ratedWatts,
    addedAt: dto.createdAt ? Date.parse(dto.createdAt) : Date.now(),
    dailyHours: dto.dailyHours,
    relayChannel: dto.relayChannel ?? null,
    simAuto: dto.simAuto ?? true,
  };
}

function itemToWrite(item: InventoryItem): ApplianceWrite & { name: string } {
  return {
    id: item.id,
    roomId: item.roomId || null,
    catalogueId: item.catalogueId || null,
    name: item.name,
    category: item.category,
    iconType: item.iconType,
    ratedWatts: item.ratedWatts,
    quantity: item.quantity,
    dailyHours: item.dailyHours ?? 0,
    isEssential: item.isEssential ?? null,
    brand: item.brand ?? null,
    model: item.model ?? null,
    relayChannel: item.relayChannel ?? null,
    simAuto: item.simAuto ?? true,
  };
}

const clampQty = (q: number) => Math.max(1, Math.min(99, Math.round(q)));
const clampHours = (h: number) => Math.max(0, Math.min(24, Math.round(Number(h) * 2) / 2));

/** Rooms and appliance inventory, persisted in the backend (rooms / appliances tables). */
export function InventoryProvider({ children }: { children: React.ReactNode }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roomsRef = useRef(rooms);
  const inventoryRef = useRef(inventory);
  useLayoutEffect(() => {
    roomsRef.current = rooms;
    inventoryRef.current = inventory;
  }, [rooms, inventory]);
  // Room creations still in flight: appliance writes into such a room wait for it.
  const pendingRooms = useRef<Map<string, Promise<unknown>>>(new Map());
  const afterRoom = <T,>(roomId: string | null | undefined, request: () => Promise<T>): Promise<T> => {
    const pending = roomId ? pendingRooms.current.get(roomId) : undefined;
    return pending ? pending.then(request) : request();
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [roomDTOs, applianceDTOs] = await Promise.all([fetchRooms(), fetchAppliances()]);
      setRooms(roomDTOs.map(roomFromDTO));
      setInventory(applianceDTOs.map(itemFromDTO).sort((a, b) => b.addedAt - a.addedAt));
      setLoaded(true);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useLoadOnConnection(refresh);

  /** Run a backend write; on failure show the error and reload server state. */
  const sync = useCallback(
    (action: string, request: Promise<unknown>) => {
      request
        .then(() => setError(null))
        .catch((e) => {
          // reload server state first, then report (refresh clears errors on success)
          void refresh().then(() => setError(`Could not ${action}: ${errorMessage(e)}`));
        });
    },
    [refresh]
  );

  const patchItem = (itemId: string, patch: Partial<InventoryItem>, write: ApplianceWrite, action: string) => {
    // keep the ref current immediately so back-to-back taps see the latest quantities
    inventoryRef.current = inventoryRef.current.map((i) => (i.id === itemId ? { ...i, ...patch } : i));
    setInventory((prev) => prev.map((i) => (i.id === itemId ? { ...i, ...patch } : i)));
    sync(action, updateAppliance(itemId, write));
  };

  const addAppliance = (
    catalogueItem: CatalogueItem,
    roomId: string,
    quantity: number,
    metadata?: { brand?: string; model?: string; isEssential?: EssentialStatus; relayChannel?: number | null; dailyHours?: number; simAuto?: boolean }
  ) => {
    const qty = clampQty(quantity);
    const relayChannel = metadata?.relayChannel ?? null;
    // A relay-controlled appliance is its own entry — never merged into an existing one.
    const existing =
      relayChannel == null
        ? inventoryRef.current.find(
            (i) => i.catalogueId === catalogueItem.id && i.roomId === roomId && i.relayChannel == null
          )
        : undefined;
    if (existing) {
      const nextQty = existing.quantity + qty;
      patchItem(existing.id, { quantity: nextQty }, { quantity: nextQty }, 'update the appliance');
      return;
    }
    const item: InventoryItem = {
      id: newId('app'),
      catalogueId: catalogueItem.id,
      name: catalogueItem.name,
      brand: metadata?.brand?.trim() || catalogueItem.brand,
      model: metadata?.model?.trim() || undefined,
      isEssential: metadata?.isEssential,
      category: catalogueItem.category,
      iconType: catalogueItem.iconType,
      roomId,
      quantity: qty,
      ratedWatts: catalogueItem.ratedWatts,
      isExample: catalogueItem.isExample,
      addedAt: Date.now(),
      dailyHours: metadata?.dailyHours != null ? clampHours(metadata.dailyHours) : getDefaultDailyHours(catalogueItem.category),
      relayChannel,
      simAuto: metadata?.simAuto ?? true,
    };
    inventoryRef.current = [item, ...inventoryRef.current];
    setInventory((prev) => [item, ...prev]);
    sync('add the appliance', afterRoom(roomId, () => createAppliance(itemToWrite(item))));
  };

  const removeAppliance = (itemId: string) => {
    setInventory((prev) => prev.filter((i) => i.id !== itemId));
    sync('remove the appliance', deleteAppliance(itemId));
  };

  const updateQuantity = (itemId: string, delta: number) => {
    const item = inventoryRef.current.find((i) => i.id === itemId);
    if (!item) return;
    const next = item.quantity + delta;
    if (next <= 0) removeAppliance(itemId);
    else patchItem(itemId, { quantity: next }, { quantity: next }, 'update the quantity');
  };

  const setQuantity = (itemId: string, quantity: number) => {
    const qty = clampQty(quantity);
    patchItem(itemId, { quantity: qty }, { quantity: qty }, 'update the quantity');
  };

  const updateRoom = (itemId: string, newRoomId: string) => {
    const item = inventoryRef.current.find((i) => i.id === itemId);
    if (!item) return;
    const target = inventoryRef.current.find(
      (i) =>
        i.id !== itemId &&
        i.catalogueId &&
        i.catalogueId === item.catalogueId &&
        i.roomId === newRoomId &&
        i.relayChannel == null &&
        item.relayChannel == null
    );
    if (target) {
      // Same appliance already in the destination room → merge quantities
      const merged = target.quantity + item.quantity;
      setInventory((prev) =>
        prev.filter((i) => i.id !== itemId).map((i) => (i.id === target.id ? { ...i, quantity: merged } : i))
      );
      sync('move the appliance', updateAppliance(target.id, { quantity: merged }).then(() => deleteAppliance(itemId)));
    } else {
      setInventory((prev) => prev.map((i) => (i.id === itemId ? { ...i, roomId: newRoomId } : i)));
      sync('move the appliance', afterRoom(newRoomId, () => updateAppliance(itemId, { roomId: newRoomId || null })));
    }
  };

  const addCustomRoom = (roomName: string): Room | null => {
    const trimmed = roomName.trim();
    if (!trimmed) return null;
    if (roomsRef.current.some((r) => r.name.toLowerCase() === trimmed.toLowerCase())) return null;
    const room: Room = { id: newId('room-custom'), name: trimmed, icon: '🏠', isCustom: true };
    setRooms((prev) => [...prev, room]);
    const request = createRoom({ id: room.id, name: trimmed, roomType: 'custom' });
    pendingRooms.current.set(room.id, request.catch(() => undefined));
    request.finally(() => pendingRooms.current.delete(room.id)).catch(() => undefined);
    sync('add the room', request);
    return room;
  };

  const updateDailyHours = (itemId: string, hours: number) => {
    const h = clampHours(hours);
    patchItem(itemId, { dailyHours: h }, { dailyHours: h }, 'update daily hours');
  };

  const updateApplianceDetails = (
    itemId: string,
    updates: {
      brand?: string;
      model?: string;
      isEssential?: EssentialStatus;
      ratedWatts?: number;
      quantity?: number;
      roomId?: string;
      dailyHours?: number;
      relayChannel?: number | null;
      simAuto?: boolean;
    }
  ) => {
    const item = inventoryRef.current.find((i) => i.id === itemId);
    if (!item) return;
    const patch: Partial<InventoryItem> = {};
    const write: ApplianceWrite = {};
    if (updates.brand !== undefined) {
      patch.brand = updates.brand.trim() || undefined;
      write.brand = patch.brand ?? null;
    }
    if (updates.model !== undefined) {
      patch.model = updates.model.trim() || undefined;
      write.model = patch.model ?? null;
    }
    if (updates.isEssential !== undefined) {
      patch.isEssential = updates.isEssential;
      write.isEssential = updates.isEssential;
    }
    if (typeof updates.ratedWatts === 'number' && updates.ratedWatts > 0) {
      patch.ratedWatts = updates.ratedWatts;
      write.ratedWatts = updates.ratedWatts;
      const catalogue = CATALOGUE.get(item.catalogueId);
      patch.isExample = !!catalogue && catalogue.isExample && catalogue.ratedWatts === updates.ratedWatts;
    }
    if (typeof updates.quantity === 'number' && updates.quantity > 0) {
      patch.quantity = clampQty(updates.quantity);
      write.quantity = patch.quantity;
    }
    if (updates.roomId) {
      patch.roomId = updates.roomId;
      write.roomId = updates.roomId;
    }
    if (typeof updates.dailyHours === 'number' && !Number.isNaN(updates.dailyHours)) {
      patch.dailyHours = clampHours(updates.dailyHours);
      write.dailyHours = patch.dailyHours;
    }
    if (updates.relayChannel !== undefined) {
      patch.relayChannel = updates.relayChannel;
      write.relayChannel = updates.relayChannel;
    }
    if (updates.simAuto !== undefined) {
      patch.simAuto = updates.simAuto;
      write.simAuto = updates.simAuto;
    }
    if (Object.keys(write).length === 0) return;
    setInventory((prev) => prev.map((i) => (i.id === itemId ? { ...i, ...patch } : i)));
    sync('save appliance details', afterRoom(write.roomId, () => updateAppliance(itemId, write)));
  };

  const totalEntries = inventory.length;
  const totalQuantity = inventory.reduce((sum, item) => sum + item.quantity, 0);
  const totalConfiguredRatedWatts = inventory.reduce((sum, item) => sum + (item.ratedWatts || 0) * item.quantity, 0);

  return (
    <InventoryContext.Provider
      value={{
        rooms,
        inventory,
        addAppliance,
        updateQuantity,
        setQuantity,
        updateRoom,
        removeAppliance,
        addCustomRoom,
        updateDailyHours,
        updateApplianceDetails,
        totalEntries,
        totalQuantity,
        totalConfiguredRatedWatts,
        loading,
        loaded,
        error,
        refresh,
      }}
    >
      {children}
    </InventoryContext.Provider>
  );
}
