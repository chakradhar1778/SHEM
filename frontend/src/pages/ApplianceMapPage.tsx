import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useInventory } from '../hooks/useInventory';
import { useLiveData } from '../hooks/useLiveData';
import { ApplianceIcon } from '../components/appliances/ApplianceIcons';
import { SourceTag } from '../components/appliances/SourceTag';
import { RoomIcon } from '../components/ui/RoomIcon';
import { PageHero } from '../components/art/PageHero';
import { ChevronRight, PlusIcon } from '../components/ui/icons';
import type { InventoryItem } from '../context/inventoryContextDef';
import './ApplianceMapPage.css';

type Status = 'on' | 'off' | 'untracked';

/** Rooms laid out as a floor plan with each appliance pinned in its room. */
export function ApplianceMapPage() {
  const { rooms, inventory } = useInventory();
  const { relay, simById } = useLiveData();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Relay appliances report the relay state; simulated appliances report the simulator state.
  const statusOf = (item: InventoryItem): Status => {
    if (item.relayChannel == null) {
      const live = simById[item.id];
      return !live ? 'untracked' : live.state === 'ON' ? 'on' : 'off';
    }
    return !relay?.commandedState ? 'untracked' : relay.commandedState === 'ON' ? 'on' : 'off';
  };

  const counts = useMemo(() => {
    const c = { on: 0, off: 0, untracked: 0 };
    for (const i of inventory) c[statusOf(i)] += i.quantity;
    return c;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inventory, relay, simById]);

  const selected = inventory.find((i) => i.id === selectedId) ?? null;
  const unplaced = inventory.filter((i) => !rooms.some((r) => r.id === i.roomId));
  const statusLabel: Record<Status, string> = { on: 'Switched on', off: 'Switched off', untracked: 'Not tracked' };

  return (
    <div className="page">
      <PageHero art="villa" title={<>Appliance<br />map</>} subtitle="See where your appliances are around your home." />

      <section className="card map" aria-label="Floor plan">
        {rooms.length === 0 ? (
          <div className="empty"><span><strong>No rooms yet.</strong>Add rooms and appliances in Devices.</span></div>
        ) : (
          <div className="map__plan">
            {rooms.map((room) => {
              const items = inventory.filter((i) => i.roomId === room.id);
              return (
                <div key={room.id} className="map__room">
                  <span className="map__room-name"><RoomIcon name={room.name} size={18} /> {room.name}</span>
                  <div className="map__pins">
                    {items.length === 0 && <span className="map__empty">Empty</span>}
                    {items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`pin pin--${statusOf(item)} ${selectedId === item.id ? 'is-selected' : ''}`}
                        onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}
                        aria-label={`${item.name}, ${statusLabel[statusOf(item)]}`}
                      >
                        <ApplianceIcon type={item.iconType} size={26} />
                        {item.quantity > 1 && <b>{item.quantity}</b>}
                        <i />
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {selected && (
          <Link to={`/devices/edit/${selected.id}`} className="map__popover">
            <ApplianceIcon type={selected.iconType} size={30} />
            <span>
              <b>{selected.name}{selected.quantity > 1 ? ` × ${selected.quantity}` : ''}</b>
              <span>{selected.ratedWatts} W · {statusLabel[statusOf(selected)]}{selected.relayChannel == null ? ' · Simulated' : ''}</span>
            </span>
            <ChevronRight />
          </Link>
        )}
      </section>

      <section className="legend-card" aria-label="Status legend">
        <div><i className="dot dot--on" /><b>{counts.on}</b><span>Switched on</span></div>
        <div><i className="dot dot--off" /><b>{counts.off}</b><span>Switched off</span></div>
        <div><i className="dot dot--untracked" /><b>{counts.untracked}</b><span>Not tracked</span></div>
      </section>

      <section className="card" aria-label="Devices in your home">
        <div className="card__head">
          <h2 className="card__title">Devices in your home</h2>
          <Link to="/devices/add" className="link-more"><PlusIcon size={14} /> Add</Link>
        </div>
        {inventory.length === 0 ? (
          <div className="empty"><span><strong>No appliances yet.</strong>Add some to see them on the map.</span></div>
        ) : (
          <div className="list">
            {inventory.map((item) => {
              const s = statusOf(item);
              return (
                <Link key={item.id} to={`/devices/edit/${item.id}`} className="row">
                  <span className="row__icon"><ApplianceIcon type={item.iconType} size={34} /></span>
                  <span className="row__body">
                    <span className="row__title">{item.name}{item.quantity > 1 ? ` × ${item.quantity}` : ''}</span>
                    <span className="row__sub">
                      <SourceTag source={item.relayChannel != null ? 'metered' : 'simulated'} compact />{' '}
                      {rooms.find((r) => r.id === item.roomId)?.name ?? 'No room'} · {item.ratedWatts} W
                    </span>
                  </span>
                  <span className={`state-pill ${s === 'on' ? 'is-on' : ''}`}>{statusLabel[s]}</span>
                </Link>
              );
            })}
          </div>
        )}
        {unplaced.length > 0 && <p className="source-note">{unplaced.length} appliance(s) have no room and aren’t shown on the plan.</p>}
        <p className="source-note">The relay appliance is measured by the SHEM meter; appliances without a relay are simulated devices.</p>
      </section>
    </div>
  );
}
